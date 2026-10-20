"""dev4 department service: QA gate (13), Data/ops KPIs (12), HR (10), Design (11), event log, approvals, webhooks.
REST + MCP (streamable HTTP at /mcp) on one port (default 8810)."""
import asyncio, json, os, sys, threading
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, FileResponse, HTMLResponse
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
import events, qa, ops, depts
import auto, actions, flows  # automation engine + executors + built-in rules (W1)

ROOT = os.path.dirname(os.path.abspath(__file__))
HOOKS_FILE = f"{ROOT}/data/webhooks.json"
HOOK_LOG = f"{ROOT}/logs/webhooks.log"
PORT = int(os.environ.get("DEPT_PORT", "8810"))
HOST = os.environ.get("DEPT_HOST", "127.0.0.1")
_lock = threading.Lock()

mcp = FastMCP("team-masala-dev4-departments", host=HOST, port=PORT, stateless_http=True, json_response=True,
              transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))

# ---------- webhooks ----------
def _hooks():
    try: return json.load(open(HOOKS_FILE))
    except Exception: return []

def _log_hook(msg):
    with open(HOOK_LOG, "a") as f: f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")

def _fanout(ev):
    o = ev.get("output") or {}
    if ev.get("status") not in ("approved", "rejected") and not (o.get("kind") == "task" and ev.get("status") == "queued") \
       and not (ev.get("status") == "done" and isinstance(o.get("action"), dict)): return
    targets = {ev["dept"]}
    if ev["dept"] == "qa": targets.add((ev.get("output") or {}).get("for_dept"))
    urls = [h["url"] for h in _hooks() if h.get("dept") in targets or h.get("dept") == "all"]
    def send():
        for u in urls:
            try:
                r = httpx.post(u, json=ev, timeout=5); _log_hook(f"OK {r.status_code} {u} task={ev['task_id']} {ev['status']}")
            except Exception as e:
                _log_hook(f"FAIL {u} task={ev['task_id']} {ev['status']}: {type(e).__name__}: {e}")
    if urls: threading.Thread(target=send, daemon=True).start()
events.HOOKS.append(_fanout)

# ---------- helpers ----------
async def _body(req):
    try: return await req.json()
    except Exception: return None

def _err(msg, code=400): return JSONResponse({"ok": False, "error": msg}, status_code=code)

def _filter(task_id=None, dept=None, status=None, limit=200):
    evs = events.read_all()
    if task_id: evs = [e for e in evs if e.get("task_id") == task_id]
    if dept: evs = [e for e in evs if e.get("dept") == dept.lower()]
    if status: evs = [e for e in evs if e.get("status") == status]
    return evs[-limit:]

def _pending():
    latest = {}
    for e in events.read_all():
        if e.get("dept") == "founder": continue
        latest[e["task_id"]] = e
    # report the originating dept (not the qa event) where possible
    out = []
    for tid, e in latest.items():
        if e.get("status") != "needs_approval": continue
        orig = [x for x in _filter(task_id=tid) if x.get("dept") != "qa"]
        src = orig[-1] if orig else e
        dept = src["dept"] if orig else ((e.get("output") or {}).get("for_dept") or e["dept"])
        out.append({"task_id": tid, "dept": dept, "summary": src["summary"], "since": e["ts"],
                    "mode": src["mode"], "output": src.get("output", {})})
    return out

def _decide(task_id, decision, note=""):
    if decision not in ("approved", "rejected"): raise ValueError("decision must be 'approved' or 'rejected'")
    p = [x for x in _pending() if x["task_id"] == task_id]
    if not p: raise LookupError(f"task {task_id} is not pending founder approval")
    src = p[0]
    with _lock:
        return events.emit(src["dept"], task_id, decision, f"Founder {decision}: {src['summary']}"[:200], src["mode"],
                           {"decision": decision, "note": note[:500], "by": "founder"}, actor="founder")

def _kpis():
    """ops.kpis, with pending approvals computed by the same logic as GET /api/approvals (single source of truth)."""
    k = ops.kpis(); p = _pending()
    k["pending_founder_approvals"] = {"count": len(p), "items": [{"task_id": x["task_id"], "dept": x["dept"],
                                      "summary": x["summary"], "since": x["since"]} for x in p]}
    return k

# ---------- REST ----------
@mcp.custom_route("/health", methods=["GET"])
async def health(req: Request):
    return JSONResponse({"ok": True, "service": "dev4-departments", "port": PORT,
                         "xai_key": bool(os.environ.get("XAI_API_KEY")),
                         "modes": {"qa": "rules+llm" if os.environ.get("XAI_API_KEY") else "rules_only",
                                   "hr": "live" if depts.live() else "mock", "design": "live" if depts.live() else "mock",
                                   "ops": "live"}})

@mcp.custom_route("/api/events", methods=["POST", "GET"])
async def api_events(req: Request):
    if req.method == "GET":
        q = req.query_params
        return JSONResponse({"events": _filter(q.get("task_id"), q.get("dept"), q.get("status"), int(q.get("limit", 200)))})
    b = await _body(req)
    try:
        with _lock: ev = events.append(b)
    except ValueError as e: return _err(str(e))
    return JSONResponse({"ok": True, "event": ev})

@mcp.custom_route("/api/qa/check", methods=["POST"])
async def api_qa(req: Request):
    b = await _body(req)
    if not isinstance(b, dict): return _err("body must be JSON object")
    try: return JSONResponse(await asyncio.to_thread(qa.check, b))
    except ValueError as e: return _err(str(e))

@mcp.custom_route("/api/ops/kpis", methods=["GET"])
async def api_kpis(req: Request):
    return JSONResponse(await asyncio.to_thread(_kpis))

@mcp.custom_route("/api/approvals", methods=["GET"])
async def api_approvals(req: Request):
    if req.query_params.get("pending", "true").lower() in ("true", "1", "yes"):
        return JSONResponse({"pending": _pending()})
    return JSONResponse({"decisions": [e for e in events.read_all() if e.get("actor") == "founder" and e["status"] in ("approved", "rejected")]})

@mcp.custom_route("/api/approvals/{task_id}", methods=["POST"])
async def api_decide(req: Request):
    b = await _body(req) or {}
    try: ev = _decide(req.path_params["task_id"], b.get("decision", ""), b.get("note", ""))
    except ValueError as e: return _err(str(e))
    except LookupError as e: return _err(str(e), 404)
    return JSONResponse({"ok": True, "event": ev})

@mcp.custom_route("/api/webhooks", methods=["POST", "GET"])
async def api_webhooks(req: Request):
    if req.method == "GET": return JSONResponse({"webhooks": _hooks()})
    b = await _body(req) or {}
    url, dept = b.get("url", ""), (b.get("dept") or "").lower()
    if not url.startswith(("http://", "https://")) or not dept: return _err("need {url: http(s)://..., dept}")
    with _lock:
        hs = [h for h in _hooks() if not (h["url"] == url and h["dept"] == dept)] + [{"url": url, "dept": dept}]
        json.dump(hs, open(HOOKS_FILE, "w"), indent=1)
    return JSONResponse({"ok": True, "webhooks": hs})

@mcp.custom_route("/api/founder/away", methods=["POST"])
async def api_away(req: Request):
    b = await _body(req) or {}
    away = bool(b.get("away", True))
    with _lock:
        ev = events.emit("founder", events.new_task_id("presence"), "done", "Founder is away (laptop closed)" if away else "Founder is back",
                         "live", {"away": away}, actor="founder")
    return JSONResponse({"ok": True, "event": ev})

@mcp.custom_route("/api/hr/run", methods=["POST"])
async def api_hr(req: Request):
    return JSONResponse(await asyncio.to_thread(depts.hr_run, await _body(req) or {}))

@mcp.custom_route("/api/design/run", methods=["POST"])
async def api_design(req: Request):
    return JSONResponse(await asyncio.to_thread(depts.design_run, await _body(req) or {}))

# ---------- MCP tools ----------
@mcp.tool(name="qa.check")
async def qa_check(dept: str, task_id: str, kind: str, content: str, context: str = "") -> dict:
    """QA approval gate. kind: customer_reply|outbound_email|refund|payment|public_post|internal (also discount|legal|pricing).
    Returns {verdict: pass|fail|founder, score, reasons, checks}. pass -> may send; fail -> revise once and re-check; founder -> do not send, queued for founder."""
    return await asyncio.to_thread(qa.check, {"dept": dept, "task_id": task_id, "kind": kind, "content": content, "context": context})

@mcp.tool(name="events.append")
async def events_append(dept: str, task_id: str, status: str, summary: str, mode: str, output: dict | None = None,
                        parent_id: str = "", actor: str = "", needs_approval: bool | None = None) -> dict:
    """Append one event to the shared log. status: queued|running|needs_approval|approved|rejected|done|failed; mode: live|mock."""
    with _lock: return events.emit(dept, task_id, status, summary, mode, output, parent_id or None, actor or None, needs_approval)

@mcp.tool(name="ops.kpis")
async def ops_kpis() -> dict:
    """Fixed ops KPIs: tasks per dept by status, pending founder approvals, avg time-to-done, replies sent while founder away."""
    return await asyncio.to_thread(_kpis)

@mcp.tool(name="approvals.pending")
async def approvals_pending() -> list:
    """Items waiting for founder approval."""
    return _pending()

@mcp.tool(name="approvals.decide")
async def approvals_decide(task_id: str, decision: str, note: str = "") -> dict:
    """Founder decision on a pending item. decision: approved|rejected. Approve -> the engine executes the action
    (outbox email / publish); reject -> revise once with the note, 2nd reject -> failed. Only call with the founder's explicit decision."""
    return _decide(task_id, decision, note)

@mcp.tool(name="automation.rules")
async def automation_rules() -> list:
    """The automation rule table: what event triggers what action."""
    return auto.list_rules()

@mcp.tool(name="hr.run")
async def hr_run(job_text: str = "", resumes: list[str] | None = None, top_k: int = 3, parent_id: str = "") -> dict:
    """HR dept: shortlist candidates + draft outreach (open_recruiter when XAI key set, else labeled mock). Output goes through qa.check."""
    return await asyncio.to_thread(depts.hr_run, {"job_text": job_text, "resumes": resumes, "top_k": top_k, "parent_id": parent_id or None})

@mcp.tool(name="design.run")
async def design_run(brand: str, brief: str, n_posts: int = 2, parent_id: str = "") -> dict:
    """Design dept: brand kit (logo + up to 2 social posts) via Grok-MCP when XAI key set, else labeled mock SVGs. Caption goes through qa.check."""
    return await asyncio.to_thread(depts.design_run, {"brand": brand, "brief": brief, "n_posts": n_posts, "parent_id": parent_id or None})

# ---------- automation, dashboard, files (W1: T01/T08) ----------
@mcp.custom_route("/api/automation/rules", methods=["GET"])
async def api_rules(req: Request):
    return JSONResponse({"rules": auto.list_rules(), "max_hops": auto.MAX_HOPS, "queue": auto._q.qsize()})

PLACEHOLDER = """<!doctype html><html><head><meta charset=utf-8><title>dev4 dashboard (placeholder)</title></head>
<body style="font-family:sans-serif"><h1>Team Masala dev4 departments</h1><p>Dashboard is being built (static/dashboard.html missing).
MOCK mode labels apply. Live data: <a href="/api/events?limit=50">events</a> | <a href="/api/approvals">approvals</a> |
<a href="/api/ops/kpis">KPIs</a> | <a href="/api/automation/rules">rules</a></p></body></html>"""

@mcp.custom_route("/dashboard", methods=["GET"])
async def dashboard(req: Request):
    f = f"{ROOT}/static/dashboard.html"
    if os.path.isfile(f): return FileResponse(f, media_type="text/html", headers={"Cache-Control": "no-store"})
    return HTMLResponse(PLACEHOLDER)

@mcp.custom_route("/", methods=["GET"])
async def root(req: Request):
    from starlette.responses import RedirectResponse
    return RedirectResponse("/dashboard")

FILE_ROOTS = {"published": f"{ROOT}/data/published", "outbox": f"{ROOT}/data/outbox", "design-out": f"{ROOT}/design-out",
              "onboarding": f"{ROOT}/data/hr/onboarding"}
TYPES = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
         ".json": "application/json", ".eml": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8", ".txt": "text/plain; charset=utf-8"}

@mcp.custom_route("/files/{path:path}", methods=["GET"])
async def files(req: Request):
    raw = req.url.path[len("/files/"):] if req.url.path.startswith("/files/") else req.path_params.get("path", "")
    parts = [p for p in raw.split("/") if p]
    if not parts or any(p in ("..", ".") or "\\" in p or "\x00" in p for p in parts) or ".." in raw:
        return _err("bad path", 400)
    base = FILE_ROOTS.get(parts[0])
    if not base: return _err(f"unknown root; use one of {sorted(FILE_ROOTS)}", 400)
    full = os.path.realpath(os.path.join(base, *parts[1:]))
    if not full.startswith(os.path.realpath(base) + os.sep): return _err("bad path", 400)
    if not os.path.isfile(full): return _err("not found", 404)
    return FileResponse(full, media_type=TYPES.get(os.path.splitext(full)[1].lower(), "application/octet-stream"))

# ---------- N01: SSE live feed (dashboard keeps 2s polling as fallback) ----------
from starlette.responses import StreamingResponse
_subs = []  # (loop, asyncio.Queue)
def _sse_hook(ev):
    for loop, q in list(_subs):
        try: loop.call_soon_threadsafe(q.put_nowait, ev)
        except Exception: pass
events.HOOKS.append(_sse_hook)

@mcp.custom_route("/api/stream", methods=["GET"])
async def api_stream(req: Request):
    q = asyncio.Queue(); sub = (asyncio.get_running_loop(), q); _subs.append(sub)
    async def gen():
        try:
            yield "retry: 2000\n: connected\n\n"
            while True:
                try: ev = await asyncio.wait_for(q.get(), timeout=15); yield f"event: event\ndata: {json.dumps(ev)}\n\n"
                except asyncio.TimeoutError: yield ": ping\n\n"
                if await req.is_disconnected(): break
        finally:
            if sub in _subs: _subs.remove(sub)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

# ---------- W3 modules (one line each; never break startup) ----------
import importlib, traceback
for _m in ("inbound", "sched", "chains", "demo", "qa_golden", "ops_ask"):
    try:
        importlib.import_module(_m).register(mcp); print(f"MODULE {_m} registered", flush=True)
    except ModuleNotFoundError as _e:
        if _e.name == _m: print(f"MODULE {_m} not present (skipped)", flush=True)
        else: print(f"MODULE {_m} FAILED: {traceback.format_exc()[-600:]}", flush=True)
    except Exception:
        print(f"MODULE {_m} FAILED: {traceback.format_exc()[-600:]}", flush=True)
auto.start()

if __name__ == "__main__":
    os.makedirs(f"{ROOT}/logs", exist_ok=True)
    mcp.run(transport="streamable-http")
