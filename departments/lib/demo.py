"""T11 (W3): demo scenario seed (PLAN section 4). POST /api/demo/seed {pace_sec?} starts it in a background thread and
returns at once; GET /api/demo/status shows progress. The dashboard "Run demo" button and demo.sh both call it.
Every seed event carries actor "demo-seed:<dept bot>" so the feed shows they are scripted triggers; everything after each
trigger is done by the automation engine (actor auto) with no other call."""
import threading, time
from datetime import datetime, timedelta, timezone
from starlette.requests import Request
from starlette.responses import JSONResponse
import events, sched

REST = None  # set to base URL when run as a script (python lib/demo.py): same steps through the REST API

def _append(ev):
    if REST:
        import httpx; r = httpx.post(REST + "/api/events", json=ev, timeout=30); r.raise_for_status(); return r.json()["event"]
    return events.append(ev)

def _emit(dept, task_id, status, summary, mode, output=None, parent_id=None, actor=None, needs_approval=None):
    ev = {"dept": dept, "task_id": task_id, "status": status, "summary": summary, "mode": mode, "output": output or {}}
    if parent_id: ev["parent_id"] = parent_id
    if actor: ev["actor"] = actor
    if needs_approval is not None: ev["needs_approval"] = needs_approval
    return _append(ev)

def _scan(actor):
    if REST:
        import httpx; return httpx.post(REST + "/api/ops/scan", json={"actor": actor}, timeout=60).json()
    return sched.scan(actor)

STATE = {"running": False, "run_id": None, "steps": [], "started": None, "finished": None}
_lock = threading.Lock()

def _ts_ago(minutes):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

def _step(name, fn):
    t0 = time.time()
    try: r = fn(); STATE["steps"].append({"step": name, "ok": True, "sec": round(time.time() - t0, 2), "ref": r})
    except Exception as e: STATE["steps"].append({"step": name, "ok": False, "error": f"{type(e).__name__}: {e}"[:200]})

def run(pace_sec=4.0, run_id=None):
    rid = run_id or events.new_task_id("demo")
    p = max(0.0, min(15.0, float(pace_sec)))
    def away(flag):
        return _emit("founder", events.new_task_id("presence"), "done",
                           "Founder is away (laptop closed)" if flag else "Founder is back", "live", {"away": flag, "demo": rid},
                           actor="founder")["task_id"]
    def trig(dept, tid, summary, output, actor):
        return _emit(dept, f"{rid}-{tid}", "done", summary, "live", {**output, "demo": rid}, None, actor)["task_id"]
    _step("1 founder away on", lambda: away(True)); time.sleep(p)
    _step("2 engineering hire_needed -> HR -> QA -> founder queue", lambda: trig(
        "engineering", "hire", "Engineering: hire needed - founding support/ops lead",
        {"kind": "hire_needed", "role": "Founding support/ops lead",
         "job_text": "Founding support/ops lead: customer support, Zendesk, SQL, writing help-center docs, on-call rota."},
        "demo-seed:engineering-bot")); time.sleep(p)
    _step("3 sales design_request -> Design -> QA pass -> auto-publish", lambda: trig(
        "sales", "design", "Sales: design request - launch kit", {"kind": "design_request", "brand": "Masala Coffee",
        "brief": "Launch visuals for a small-batch coffee subscription", "n_posts": 1}, "demo-seed:sales-bot")); time.sleep(p)
    _step("4 support design_request with contact info in caption -> QA fail -> revise -> pass -> publish", lambda: trig(
        "support", "badcap", "Support: design request - help-center banner", {"kind": "design_request", "brand": "Masala Help",
        "brief": "Help-center banner", "caption": "Need help? Email founder@masala-demo.example.com or call 512-555-0147 today!",
        "n_posts": 0}, "demo-seed:support-bot")); time.sleep(p)
    _step("5 support reply via needs_qa -> QA pass -> cleared", lambda: _emit(
        "support", f"{rid}-reply", "running", "Support: reply draft for order #42", "mock",
        {"needs_qa": True, "kind": "customer_reply", "content": "Hi Sam, thanks for reaching out! Your order shipped today and should arrive Thursday.",
         "context": "Customer asked where order #42 is.", "demo": rid}, None, "demo-seed:support-bot")["task_id"]); time.sleep(p)
    def anomaly():
        _append({"dept": "support", "task_id": f"{rid}-refund", "status": "needs_approval", "ts": _ts_ago(11), "mode": "mock",
                       "summary": "Support: refund reply waiting for founder (DEMO SEED, backdated 11 min)", "actor": "demo-seed:support-bot",
                       "output": {"kind": "refund", "content": "We can refund your $20 order.", "demo": rid, "backdated_min": 11}})
        return _scan("ops-scheduler")["tasks_created"]
    _step("6 ops anomaly: support approval backdated 11 min (DEMO SEED) -> ops.scan -> task for support", anomaly); time.sleep(p)
    _step("7 founder back", lambda: away(False))
    return rid

def start(pace_sec=4.0):
    with _lock:
        if STATE["running"]: return {"ok": False, "error": "demo already running", **STATE}
        rid = events.new_task_id("demo")
        STATE.update(running=True, run_id=rid, steps=[], started=events.now_iso(), finished=None)
    def go():
        try: run(pace_sec, rid)
        finally: STATE.update(running=False, finished=events.now_iso())
    threading.Thread(target=go, daemon=True, name="demo-seed").start()
    return {"ok": True, "run_id": rid, "pace_sec": pace_sec, "status": "/api/demo/status"}

def register(mcp, lock=None):
    @mcp.custom_route("/api/demo/seed", methods=["POST"])
    async def api_seed(req: Request):
        try: b = await req.json()
        except Exception: b = {}
        if (b or {}).get("scenario") == "pulse":   # Phase 2: Pulse Studio trend -> product -> listing chain
            import pulse; return JSONResponse({**pulse.start(b, "pulse"), "scenario": "pulse"})
        return JSONResponse(start(float((b or {}).get("pace_sec", 4))))

    @mcp.custom_route("/api/demo/status", methods=["GET"])
    async def api_demo_status(req: Request):
        return JSONResponse(STATE)
    return ["/api/demo/seed", "/api/demo/status"]

if __name__ == "__main__":
    import json, sys
    REST = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8810"
    STATE.update(steps=[]); rid = run(float(sys.argv[2]) if len(sys.argv) > 2 else 4.0)
    print(json.dumps({"run_id": rid, "steps": STATE["steps"]}, indent=1))
