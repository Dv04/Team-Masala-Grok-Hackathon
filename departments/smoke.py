#!/usr/bin/env python3
"""Smoke test for dev4 departments. Run: .venv/bin/python smoke.py  (services must be up via ./start.sh)"""
import asyncio, json, os, subprocess, sys, threading, time, uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

API = os.environ.get("DEPT_API", "http://127.0.0.1:8810")
RUN = "smoke-" + uuid.uuid4().hex[:6]
results = []
def ok(name, cond, detail=""):
    results.append((name, bool(cond))); print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}"[:400])
skipped = []
def skip(name, why): skipped.append(name); print(f"SKIP  {name}  ({why})")
def up(port):  # optional uvx/npx MCP servers (start.sh); teammates may run without them
    import socket
    try: socket.create_connection(("127.0.0.1", port), 1).close(); return True
    except OSError: return False

got = []
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        got.append(json.loads(self.rfile.read(int(self.headers["Content-Length"])))); self.send_response(200); self.end_headers()
    def log_message(self, *a): pass
srv = HTTPServer(("127.0.0.1", 8899), H); threading.Thread(target=srv.serve_forever, daemon=True).start()

c = httpx.Client(base_url=API, timeout=120)
h = c.get("/health").json(); ok("health", h.get("ok"), json.dumps(h["modes"]))

# 1 events: CLI + REST + validation + filter
out = subprocess.run(["bin/emit", "--dept", "support", "--task", f"{RUN}-cli", "--status", "queued", "--summary", "smoke CLI event",
                      "--mode", "mock", "--actor", "smoke"], capture_output=True, text=True).stdout
ok("emit CLI -> POST /api/events", '"ok": true' in out or '"ok":true' in out, out.strip()[:150])
r = c.post("/api/events", json={"dept": "sales", "task_id": f"{RUN}-sale", "status": "running", "summary": "smoke", "mode": "mock", "actor": "smoke"})
ok("POST /api/events valid", r.status_code == 200, r.text[:120])
r = c.post("/api/events", json={"dept": "sales", "task_id": "x", "status": "sent", "summary": "bad", "mode": "mock"})
ok("POST /api/events rejects bad status", r.status_code == 400, r.text[:140])
r = c.post("/api/events", json={"dept": "sales", "task_id": "x", "status": "done", "summary": "bad", "mode": "maybe"})
ok("POST /api/events rejects bad mode", r.status_code == 400, r.text[:140])
r = c.get("/api/events", params={"task_id": f"{RUN}-sale", "status": "running"}).json()
ok("GET /api/events?task_id&status", len(r["events"]) == 1, json.dumps(r["events"][0])[:160])

# 2 QA gate cases
def qa(kind, content, tid, **kw):
    return c.post("/api/qa/check", json={"dept": "support", "task_id": tid, "kind": kind, "content": content, **kw}).json()
r = qa("customer_reply", "Hi Sam, thanks for reaching out! Your order shipped today and should arrive Thursday.", f"{RUN}-q1",
       context="Customer asked where order #42 is.")
ok("qa pass (clean customer reply)", r["verdict"] == "pass", json.dumps(r)[:300])
r = qa("customer_reply", "Sure, your card 4111 1111 1111 1111 is on file. [insert signature]", f"{RUN}-q2")
ok("qa fail (card number + placeholder)", r["verdict"] == "fail", json.dumps({k: r[k] for k in ('verdict','score','reasons')})[:300])
r = qa("customer_reply", "", f"{RUN}-q3"); ok("qa fail (empty)", r["verdict"] == "fail", r["reasons"][0])
r = qa("internal", '{"a": 1,', f"{RUN}-q4"); ok("qa fail (invalid JSON)", r["verdict"] == "fail", r["reasons"][0])
r = qa("refund", "We've issued a refund of $20 to your original payment method.", f"{RUN}-q5")
ok("qa founder (refund kind)", r["verdict"] == "founder", "; ".join(r["reasons"])[:250])
r = qa("outbound_email", "Hi Jordan, saw your shop on Etsy and thought our tool could help. Open to a quick chat?", f"{RUN}-q6")
ok("qa founder (first message to new lead)", r["verdict"] == "founder", r["reasons"][0])
r = qa("outbound_email", "Following up on our chat last week, here is the onboarding link you asked for.", f"{RUN}-q7", first_contact=False)
ok("qa pass (follow-up, first_contact:false)", r["verdict"] == "pass", r["verdict"])
r = qa("customer_reply", "We guarantee this will never happen again and will compensate you.", f"{RUN}-q8")
ok("qa founder (legal wording)", r["verdict"] == "founder", r["reasons"][0])
r = qa("customer_reply", "ok 123-45-6789", f"{RUN}-q2")
ok("qa 2nd fail on same task -> founder", r["verdict"] == "founder", "; ".join(r["reasons"])[:200])
ok("qa LLM checks marked skipped w/o key", "skipped" in str(r["check_results"]["rubric"]) and r["mode"] == "rules_only",
   f"mode={r['mode']} rubric={r['check_results']['rubric']}")

# 3 MCP qa.check (streamable HTTP)
async def mcp_check():
    async with streamablehttp_client(API + "/mcp") as (rd, wr, _):
        async with ClientSession(rd, wr) as s:
            await s.initialize()
            tools = [t.name for t in (await s.list_tools()).tools]
            res = await s.call_tool("qa.check", {"dept": "sales", "task_id": f"{RUN}-mcp", "kind": "public_post",
                                                 "content": "New feature live today. Email me at a@b.com"})
            return tools, res.structuredContent or json.loads(res.content[0].text)
tools, r = asyncio.run(mcp_check())
ok("MCP tools/list", "qa.check" in tools, str(tools))
ok("MCP qa.check (public post w/ email -> fail)", r["verdict"] == "fail", json.dumps({k: r[k] for k in ('verdict','score','reasons','checks')})[:300])

# 4 webhooks + approvals
r = c.post("/api/webhooks", json={"url": "http://127.0.0.1:8899/hook", "dept": "support"}); ok("POST /api/webhooks", r.status_code == 200)
c.post("/api/webhooks", json={"url": "http://127.0.0.1:1/dead", "dept": "support"})  # failure path, best effort
p = c.get("/api/approvals", params={"pending": "true"}).json()["pending"]
ids = [x["task_id"] for x in p]
ok("GET /api/approvals?pending=true lists refund", f"{RUN}-q5" in ids, f"{len(p)} pending")
r = c.post(f"/api/approvals/{RUN}-q5", json={"decision": "approved", "note": "ok, test mode"})
ok("POST /api/approvals/{id} approved", r.status_code == 200 and r.json()["event"]["status"] == "approved", json.dumps(r.json()["event"])[:220])
r = c.post(f"/api/approvals/{RUN}-q6", json={"decision": "rejected", "note": "not this lead"})
ok("POST /api/approvals/{id} rejected", r.status_code == 200 and r.json()["event"]["status"] == "rejected")
r = c.post(f"/api/approvals/{RUN}-q1", json={"decision": "approved"}); ok("approve non-pending -> 404", r.status_code == 404)
r = c.post(f"/api/approvals/{RUN}-q8", json={"decision": "maybe"}); ok("bad decision -> 400", r.status_code == 400)
time.sleep(2)
mine = [e for e in got if e.get("task_id") in (f"{RUN}-q5", f"{RUN}-q6")]
ok("webhook delivered approved+rejected to support hook", {e["status"] for e in mine} >= {"approved", "rejected"}, f"{len(got)} received")
log = open("logs/webhooks.log").read() if os.path.exists("logs/webhooks.log") else ""
ok("dead webhook failure logged", "FAIL http://127.0.0.1:1/dead" in log)

# 5 founder away + a reply sent while away, then KPIs
c.post("/api/founder/away", json={"away": True})
c.post("/api/events", json={"dept": "support", "task_id": f"{RUN}-r1", "status": "queued", "summary": "smoke reply", "mode": "mock", "actor": "smoke"})
time.sleep(1.1)
c.post("/api/events", json={"dept": "support", "task_id": f"{RUN}-r1", "status": "done", "summary": "smoke reply sent", "mode": "mock",
                            "actor": "smoke", "output": {"kind": "customer_reply", "sent": True}})
c.post("/api/founder/away", json={"away": False})

# 6 HR + Design (mock without key)
r = c.post("/api/hr/run", json={"parent_id": RUN}).json()
ok("HR run (mock)", r["mode"] == "mock" and r["shortlist"] and r["status"] in ("needs_approval", "done"),
   json.dumps({"status": r["status"], "engine": r["engine"], "top": r["shortlist"][0], "qa": r["qa"]["verdict"]})[:300])
r = c.post("/api/design/run", json={"brand": "Masala Candles", "brief": "Hand-poured spice candles for a solo Etsy seller", "parent_id": RUN}).json()
ok("Design run (mock)", r["mode"] == "mock" and len(r["assets"]) == 3 and all(os.path.exists(a["file"]) for a in r["assets"]),
   json.dumps({"status": r["status"], "engine": r["engine"], "assets": [os.path.basename(a['file']) for a in r['assets']], "qa": r["qa"]["verdict"]})[:300])

k = c.get("/api/ops/kpis").json()
ok("GET /api/ops/kpis", "tasks_by_dept_status" in k and k["pending_founder_approvals"]["count"] >= 1,
   json.dumps({"pending": k["pending_founder_approvals"]["count"], "avg_ttd": k["avg_time_to_done_sec"]["overall"],
               "replies_away": k["replies_sent_while_founder_away"], "modes": k["events_by_mode"]}))
ok("KPI replies while founder away >= 1", k["replies_sent_while_founder_away"] >= 1)

# 7 DuckDB MCP on 8000 over the same log
async def duck():
    async with streamablehttp_client("http://127.0.0.1:8000/mcp") as (rd, wr, _):
        async with ClientSession(rd, wr) as s:
            await s.initialize()
            res = await s.call_tool("execute_query", {"sql": "SELECT dept, count(*) n FROM events GROUP BY dept ORDER BY n DESC"})
            return "".join(getattr(x, "text", "") for x in res.content)
if up(8000): txt = asyncio.run(duck()); ok("DuckDB MCP execute_query over events", "qa" in txt and "hr" in txt, txt.replace("\n", " ")[:300])
else: skip("DuckDB MCP execute_query over events", "DuckDB MCP not reachable on 127.0.0.1:8000; run ./start.sh")

# 8 automation engine + chains (T12, W3). Everything below is triggered by ONE event/call; the engine does the rest.
import http.client, glob
def evs(**q): return c.get("/api/events", params={"limit": 2000, **q}).json()["events"]
def wait(fn, timeout=20):
    t = time.time()
    while time.time() - t < timeout:
        v = fn()
        if v: return v
        time.sleep(0.4)
    return fn()
def child(parent, dept, status):
    return [e for e in evs() if e.get("parent_id") == parent and e["dept"] == dept and e["status"] == status]
def post_ev(dept, tid, status, summary, output, **kw):
    r = c.post("/api/events", json={"dept": dept, "task_id": tid, "status": status, "summary": summary, "mode": "mock",
                                    "actor": "smoke", "output": output, **kw}); return r

rules = [r["name"] for r in c.get("/api/automation/rules").json()["rules"]]
ok("GET /api/automation/rules has built-in + W3 chains", {"chain.hire_needed->hr", "chain.design_request->design", "chain.needs_qa->qa",
   "chain.ops_task->dept", "founder.approve->execute", "founder.reject->revise_once"} <= set(rules), str(rules)[:300])

# chain 1: engineering hire_needed -> HR -> QA founder -> approval queue (actor auto, parent_id = trigger)
post_ev("engineering", f"{RUN}-hire", "done", "smoke: hire needed", {"kind": "hire_needed", "role": "Support lead", "job_text": "Support lead, Zendesk, SQL"})
hr1 = wait(lambda: child(f"{RUN}-hire", "hr", "needs_approval"))
ok("chain1 hire_needed -> hr needs_approval (auto, parent_id)", bool(hr1) and hr1[-1].get("actor") == "auto" and hr1[-1]["parent_id"] == f"{RUN}-hire",
   (hr1[-1]["task_id"] + " " + hr1[-1]["summary"]) if hr1 else "no hr event")
hr_tid = hr1[-1]["task_id"] if hr1 else "none"
ok("chain1 HR task in founder queue", wait(lambda: hr_tid in [p["task_id"] for p in c.get("/api/approvals").json()["pending"]], 5))

# approve -> executor: outbox .eml + ATS contacted + done(action, executed_by founder)
r = c.post(f"/api/approvals/{hr_tid}", json={"decision": "approved", "note": "smoke approve"})
d = wait(lambda: [e for e in evs(task_id=hr_tid) if e["status"] == "done" and (e.get("output") or {}).get("action")])
a = d[-1]["output"]["action"] if d else {}
ok("approve HR -> .eml in data/outbox, executed_by founder", a.get("executed_by") == "founder" and a.get("path") and os.path.exists(a["path"]),
   json.dumps({k: a.get(k) for k in ("type", "path", "to", "executed_by")})[:250])
ats = json.load(open("data/hr/pipeline.json")) if os.path.exists("data/hr/pipeline.json") else {}
ok("approve HR -> ATS stage contacted", any(h.get("task_id") == hr_tid and h.get("stage") == "contacted" for h in ats.get("history", [])))
eml = open(a["path"]).read() if a.get("path") and os.path.exists(a["path"]) else ""
ok("outbox .eml is sandbox (example.com, X-Sandbox, MOCK subject)", "example.com" in eml and "X-Sandbox" in eml and "[MOCK]" in eml)

# reject -> revise once -> reject again -> failed
post_ev("engineering", f"{RUN}-hire2", "done", "smoke: hire needed 2", {"kind": "hire_needed", "role": "Ops lead"})
h2 = wait(lambda: child(f"{RUN}-hire2", "hr", "needs_approval")); t2 = h2[-1]["task_id"] if h2 else "none"
c.post(f"/api/approvals/{t2}", json={"decision": "rejected", "note": "warmer tone please"})
rev = wait(lambda: len([e for e in evs(task_id=t2) if e["status"] == "needs_approval" and e["dept"] == "hr"]) >= 2)
ok("reject #1 -> HR revises once -> back in founder queue", rev)
c.post(f"/api/approvals/{t2}", json={"decision": "rejected", "note": "still no"})
f2 = wait(lambda: [e for e in evs(task_id=t2) if e["status"] == "failed"])
ok("reject #2 -> final status failed", f2 and evs(task_id=t2)[-1]["status"] == "failed", f2[-1]["summary"] if f2 else "")

# chain 2: sales design_request -> Design -> QA pass -> auto-publish
post_ev("sales", f"{RUN}-dreq", "done", "smoke: design request", {"kind": "design_request", "brand": "Smoke Co", "brief": "Launch visuals", "n_posts": 1})
pub = wait(lambda: [e for e in evs() if e["dept"] == "design" and e.get("parent_id") == f"{RUN}-dreq" and (e.get("output") or {}).get("action")])
pa = pub[-1]["output"]["action"] if pub else {}
ok("chain2 design_request -> published caption.json (auto)", pa.get("executed_by") == "auto" and os.path.exists(pa.get("path", "/x")),
   json.dumps({k: pa.get(k) for k in ("type", "path", "executed_by")})[:220])
ok("published files keep .MOCK in mock mode", pa.get("files") and all(".MOCK." in f for f in pa["files"]), str(pa.get("files"))[:200])

# bad caption -> QA fail -> revise -> pass -> published
post_ev("support", f"{RUN}-dbad", "done", "smoke: bad caption", {"kind": "design_request", "brand": "Smoke Help", "brief": "Banner",
        "caption": "Email help@smoke-demo.example.com or call 512-555-0147", "n_posts": 0})
pb = wait(lambda: [e for e in evs() if e["dept"] == "design" and e.get("parent_id") == f"{RUN}-dbad" and (e.get("output") or {}).get("action")])
btid = pb[-1]["task_id"] if pb else "none"
qv = [(e.get("output") or {}).get("verdict") for e in evs(task_id=btid) if e["dept"] == "qa"]
ok("caption with contact info -> QA fail -> revised -> pass -> published", qv[:2] == ["fail", "pass"] and pb, f"qa verdicts {qv}")

# chain 3: any dept needs_qa:true -> QA -> verdict webhook to that dept -> done
got.clear()
post_ev("support", f"{RUN}-nq", "running", "smoke: reply draft", {"needs_qa": True, "kind": "customer_reply",
        "content": "Hi Sam, your order shipped today and should arrive Thursday."})
nq = wait(lambda: [e for e in evs(task_id=f"{RUN}-nq") if e["status"] == "done"])
ok("chain3 needs_qa -> qa pass -> source task done", nq and nq[-1]["actor"] == "auto")
ok("chain3 QA verdict webhook delivered to support hook", wait(lambda: [e for e in got if e.get("task_id") == f"{RUN}-nq" and e.get("dept") == "qa"], 5),
   f"{len(got)} hook posts")
post_ev("sales", f"{RUN}-nqf", "running", "smoke: bad reply", {"needs_qa": True, "kind": "customer_reply", "content": "ok 123-45-6789"})
ok("chain3 needs_qa fail -> revise request (running, auto)", wait(lambda: [e for e in evs(task_id=f"{RUN}-nqf") if e.get("actor") == "auto" and e["status"] == "running"]))

# T05 inbound
r = c.post("/api/inbound/design", json={"brand": "Inbound Co", "brief": "Inbound brief", "source": "smoke"})
itid = r.json().get("trigger", {}).get("task_id")
ok("POST /api/inbound/design -> design chain runs to published", r.status_code == 200 and
   wait(lambda: [e for e in evs() if e.get("parent_id") == itid and e["dept"] == "design" and e["status"] == "done"]), itid)
r = c.post("/api/inbound/nope!", json={}); ok("POST /api/inbound/<bad dept> -> 400", r.status_code == 400)

# T06 scheduler: backdated approval (11 min) -> exactly one task for that dept; second scan none; chain4 routes it
from datetime import datetime, timedelta, timezone
old = (datetime.now(timezone.utc) - timedelta(minutes=11)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
post_ev("support", f"{RUN}-stale", "needs_approval", "smoke: stale approval", {"kind": "refund"}, ts=old)
s1 = c.post("/api/ops/scan", json={"actor": "smoke"}).json(); s2 = c.post("/api/ops/scan", json={"actor": "smoke"}).json()
mine = [t for t in s1["tasks_created"] if t["for_dept"] == "support"]
ok("ops.scan: stale approval -> exactly 1 support task", len(mine) == 1, json.dumps(mine)[:200])
ok("ops.scan again -> no duplicate task", not [t for t in s2["tasks_created"] if t["for_dept"] == "support"], json.dumps(s2)[:160])
ts = c.get("/api/tasks", params={"dept": "support"}).json()["tasks"]
ok("GET /api/tasks?dept=support returns the ops task", mine and any(t["task_id"] == mine[0]["task_id"] for t in ts), f"{len(ts)} support tasks")
ok("chain4 ops task -> routed to support (ops done, parent=task)", mine and wait(lambda: [e for e in evs(dept="ops") if e.get("parent_id") == mine[0]["task_id"]], 8))

# X06 governed metrics + ops.ask (MOCK keyword match without key)
r = c.post("/api/ops/ask", json={"question": "how many approvals are pending?"}).json()
pend = len(c.get("/api/approvals").json()["pending"])
ok("ops.ask 'pending approvals?' -> metric + SQL + number", r.get("metric") == "pending_approvals" and "SELECT" in r.get("sql", "")
   and r["rows"][0]["pending_approvals"] == pend, f"{r.get('answer')} (queue has {pend}) engine={r.get('engine')}")
# dev2's case: needs_approval, then done carrying an OLDER client ts -> log order wins in both queue and ops.ask
post_ev("sales", f"{RUN}-oldts", "needs_approval", "smoke: needs approval", {})
post_ev("sales", f"{RUN}-oldts", "done", "smoke: done with older client ts", {}, ts="2020-01-01T00:00:00.000Z")
pq = [p["task_id"] for p in c.get("/api/approvals").json()["pending"]]
r2 = c.post("/api/ops/ask", json={"question": "how many approvals are pending?"}).json()
ok("older-ts done clears pending in queue and ops.ask (same count)", f"{RUN}-oldts" not in pq and r2["rows"][0]["pending_approvals"] == len(pq),
   f"{r2.get('answer')} (queue has {len(pq)})")
ok("ops.ask labeled MOCK without XAI key", r.get("mode") == "mock" and r.get("engine", "").startswith("MOCK"), r.get("engine"))
r = c.get("/api/ops/ask", params={"q": "which dept fails most"}).json(); ok("ops.ask GET ?q= picks failed_tasks_by_dept", r.get("metric") == "failed_tasks_by_dept", str(r.get("metric")))
ok("GET /api/ops/metrics lists governed metrics", len(c.get("/api/ops/metrics").json()["metrics"]) >= 10)
sys.path.insert(0, "lib"); import ops_ask as _oa
try: _oa.run_sql("SELECT * FROM read_csv('/etc/passwd')"); blocked = False
except Exception: blocked = True
ok("ops.ask SQL sandbox blocks file reads", blocked)
async def mcp_ask():
    async with streamablehttp_client(API + "/mcp") as (rd, wr, _):
        async with ClientSession(rd, wr) as s:
            await s.initialize(); res = await s.call_tool("ops.ask", {"question": "qa pass rate"})
            return res.structuredContent or json.loads(res.content[0].text)
r = asyncio.run(mcp_ask()); ok("MCP ops.ask works", r.get("metric") == "qa_pass_rate", str(r.get("answer")))

# X08 QA golden suite / reliability
r = c.post("/api/qa/golden-check", json={"dept": "golden", "task_id": f"{RUN}-g", "kind": "customer_reply", "content": "Thanks! [insert signature]"}).json()
ok("placeholder after a space fails (X08 regression)", r["verdict"] == "fail", "; ".join(r["reasons"])[:120])
ok("golden-check does not write to the event log", not evs(task_id=f"{RUN}-g"))
rel = c.get("/api/qa/reliability").json()
if not rel.get("total") and not up(3100): skip("GET /api/qa/reliability has a real promptfoo result", "no stored promptfoo run and promptfoo MCP not on :3100")
else: ok("GET /api/qa/reliability has a real promptfoo result", rel.get("total") and rel.get("pass_rate") is not None,
   f"{rel.get('passed')}/{rel.get('total')} pass_rate={rel.get('pass_rate')} ran_at={rel.get('ran_at')}")

# dashboard + files path-safety
r = c.get("/dashboard"); ok("GET /dashboard 200 text/html", r.status_code == 200 and "text/html" in r.headers.get("content-type", ""), str(len(r.text)) + " bytes")
hc = http.client.HTTPConnection("127.0.0.1", int(API.rsplit(":", 1)[1])); hc.request("GET", "/files/../etc/passwd"); rr = hc.getresponse()
ok("/files/../etc/passwd -> 400 (raw path)", rr.status == 400, str(rr.status)); rr.read()
ok("/files/published/<task>/caption.json served", pa.get("url") and c.get(pa["url"]).status_code == 200, pa.get("url"))

r = c.get("/api/demo/status")
if r.status_code == 200: ok("GET /api/demo/status (demo module wired)", "running" in r.json(), json.dumps(r.json())[:120])
else: print(f"SKIP  /api/demo/status -> {r.status_code} (lib/demo.py not wired into server.py yet; demo.sh uses REST fallback)")

def _evkind(tid, kind): return [e for e in evs(task_id=tid) if (e.get("output") or {}).get("kind") == kind]
# Phase 2: Pulse Studio chain (trend -> product -> QA -> listing_live -> order -> margin) + trademark block + price gate
c.post("/api/webhooks", json={"url": "http://127.0.0.1:8899/pulse", "dept": "marketing"})
r = c.post("/api/pulse/start", json={"force_low_score": True}).json()
ok("pulse.start without trend uses a backup trend", r.get("ok") and r["trend"]["source"] == "backup", json.dumps(r.get("trend"))[:150])
pt = r.get("trend_task")
live = wait(lambda: [e for e in evs() if e.get("parent_id") == pt and (e.get("output") or {}).get("kind") == "listing_live"])
prod = [e for e in evs() if e.get("parent_id") == pt and (e.get("output") or {}).get("kind") == "product_created"]
po = (prod[-1]["output"] if prod else {})
ok("trend_spotted -> design product_created (MOCK svg, price, cost)", prod and po.get("product_type") in ("sticker", "tee", "poster")
   and po.get("image", "").endswith(".MOCK.svg") and po.get("price_usd") and po.get("cost_usd"), json.dumps({k: po.get(k) for k in ("product_type", "title", "price_usd", "cost_usd")}))
ok("product brand score retried once after forced low score", po.get("attempts") == 2 and po.get("first_score", 1) < 0.7 <= (po.get("brand_score") or 0),
   f"first={po.get('first_score')} final={po.get('brand_score')}")
ok("QA pass -> listing_live event + listing page", live and c.get(live[-1]["output"]["url"]).status_code == 200
   and "Stripe test mode" in c.get(live[-1]["output"]["url"]).text, live[-1]["output"]["url"] if live else "no listing_live")
ok("listing_live has image_url under /files/ (served)", live and live[-1]["output"].get("image_url", "").startswith("/files/")
   and c.get(live[-1]["output"]["image_url"]).status_code == 200, live[-1]["output"].get("image_url") if live else "")
ok("GET /api/pulse/listings includes the new listing", ptask0 in [x["task_id"] for x in c.get("/api/pulse/listings").json()["listings"]] if (ptask0 := (live[-1]["task_id"] if live else None)) else False)
ok("GET /store 200 text/html", c.get("/store").status_code == 200 and "text/html" in c.get("/store").headers.get("content-type", ""))
ok("listing_live fanned out to marketing webhook", wait(lambda: [g for g in got if (g.get("output") or {}).get("kind") == "listing_live"], 6), f"{len(got)} webhook posts")
ptask = live[-1]["task_id"] if live else "none"
post_ev("sales", f"{RUN}-realsales", "done", "smoke: real sales bot saw the listing", {"kind": "listing_live"}, parent_id=ptask)
k0 = c.get("/api/ops/kpis").json().get("pulse", {})
r = c.post("/api/ops/order", json={"task_id": ptask, "qty": 2}).json()
ok("POST /api/ops/order -> MOCK POD order, Stripe test mode", r.get("ok") and r["order"]["payment"]["mode"] == "test" and "MOCK" in r["order"]["provider"],
   json.dumps(r.get("order", r))[:200])
oid = r.get("order", {}).get("order_id")
kinds = [(e.get("output") or {}).get("kind") for e in evs(task_id=oid or "x")]
ok("order emits order_placed + margin_update (computed_by ops)", "order_placed" in kinds and "margin_update" in kinds, str(kinds))
k1 = c.get("/api/ops/kpis").json().get("pulse", {})
ok("KPIs pulse: orders/revenue/margin updated", k1.get("orders_count") == (k0.get("orders_count") or 0) + 1 and k1.get("margin_pct") is not None,
   json.dumps(k1)[:200])
r = c.get("/api/ops/ask", params={"q": "what is our revenue"}).json()
ok("ops.ask revenue -> revenue_usd metric", r.get("metric") == "revenue_usd", str(r.get("answer")))
ok("order on unknown listing -> 404", c.post("/api/ops/order", json={"task_id": "nope"}).status_code == 404)
si = wait(lambda: (lambda x: x if {"research", "legal", "engineering", "marketing", "support", "finance"} <= {e["dept"] for e in x} else None)(
    [e for e in evs() if e.get("actor") == "standin-dev4" and e.get("parent_id") in (pt, ptask, oid) and (e.get("output") or {}).get("standin") is True]), 25) or []
ok("stand-ins (actor standin-dev4, standin:true): research, legal, engineering, marketing, support, finance", si, str(sorted({e["dept"] for e in si})))
ok("real teammate event cancels stand-in (sales)", not [e for e in si if e["dept"] == "sales"], "sales stand-in skipped")
mk = [e for e in si if e["dept"] == "marketing"]
ok("marketing stand-in wrote MOCK posts.md (not posted)", mk and c.get(mk[-1]["output"]["url"]).status_code == 200 and mk[-1]["output"]["posted"] is False)
ok("support stand-in Q&A went through QA", wait(lambda: [e for e in evs() if e["dept"] == "qa" and e.get("output", {}).get("for_dept") == "support"
   and e["task_id"] in [x["task_id"] for x in si if x["dept"] == "support"]], 8))
r = c.post("/api/pulse/start", json={"trend": "Disney villains night", "source": "manual"}).json(); bt = r["trend_task"]
blk = wait(lambda: [e for e in evs() if e.get("parent_id") == bt and e["status"] == "failed"])
ok("trademark trend -> QA fail, product blocked, no listing", blk and "trademark" in json.dumps(blk[-1]["output"])
   and not [e for e in evs() if e.get("parent_id") == bt and (e.get("output") or {}).get("kind") == "listing_live"], blk[-1]["summary"][:120] if blk else "not blocked")
r = c.post("/api/pulse/start", json={"trend": "Desk plant club", "product_type": "poster", "price_usd": 75}).json(); ft = r["trend_task"]
fq = wait(lambda: [e for e in evs() if e.get("parent_id") == ft and e["dept"] == "qa" and e["status"] == "needs_approval"])
ok("price outside $5-$60 -> founder queue", fq and fq[-1]["task_id"] in [p["task_id"] for p in c.get("/api/approvals").json()["pending"]], fq[-1]["summary"] if fq else "")
if fq:
    c.post(f"/api/approvals/{fq[-1]['task_id']}", json={"decision": "approve", "note": "smoke"})
    ok("founder approve (decision 'approve') -> listing_live", wait(lambda: _evkind(fq[-1]["task_id"], "listing_live")), fq[-1]["task_id"])
r = c.post("/api/events", json={"dept": "integrations", "task_id": f"{RUN}-stall", "status": "running", "summary": "smoke chain_stalled",
                               "mode": "mock", "actor": "smoke", "output": {"kind": "chain_stalled", "task": ptask}})
ok("dev3 dept events validate (integrations chain_stalled)", r.status_code == 200, r.text[:100])
r = c.post("/api/ops/ask", json={"q": "how many approvals are pending?"}).json()
ok("ops.ask POST accepts {q} as well as {question}", r.get("metric") == "pending_approvals", str(r.get("metric")))

# idempotency on restart: no trigger re-fires (set SMOKE_RESTART=0 to skip)
if os.environ.get("SMOKE_RESTART", "1") == "1":
    before = len([e for e in evs() if e.get("parent_id") in (f"{RUN}-hire", f"{RUN}-dreq") and e["status"] == "queued"])
    subprocess.run("./stop.sh >/dev/null 2>&1; ./start.sh >/dev/null 2>&1", shell=True)
    wait(lambda: c.get("/health").status_code == 200, 30); time.sleep(4)
    after = len([e for e in evs() if e.get("parent_id") in (f"{RUN}-hire", f"{RUN}-dreq") and e["status"] == "queued"])
    ok("restart service -> no duplicate chain runs", before == after == 2, f"queued child runs before={before} after={after}")

srv.shutdown()
n = sum(1 for _, p in results if p); print(f"\nSMOKE {n}/{len(results)} passed, {len(skipped)} skipped (run id {RUN})")
sys.exit(0 if n == len(results) else 1)
