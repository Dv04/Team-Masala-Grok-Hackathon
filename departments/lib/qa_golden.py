"""X08 (W3): QA gate reliability. qa/golden.yaml is a promptfoo (MIT) suite of known-good / known-bad / founder-gated outputs
with deterministic asserts (no LLM, no key). The suite calls POST /api/qa/golden-check, which runs the SAME qa.check as
/api/qa/check but with log=False, so golden cases never enter the event log or the founder approval queue.
REST: POST /api/qa/golden-check (provider target) | GET /api/qa/reliability (last result, for the dashboard tile)
      POST /api/qa/reliability/run (start a run in the background; takes ~10-20 s)  | MCP: qa.reliability"""
import json, os, subprocess, threading, time
from datetime import datetime, timezone
from starlette.requests import Request
from starlette.responses import JSONResponse
import qa

ROOT = os.environ.get("DEPT_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUITE = f"{ROOT}/qa/golden.yaml"
RAW = f"{ROOT}/data/qa_golden_results.json"
SUMMARY = f"{ROOT}/data/qa_reliability.json"
PROMPTFOO = os.environ.get("PROMPTFOO_PKG", "promptfoo@0.124.1")
REGISTERED = False
_run_lock = threading.Lock()
STATE = {"running": False}

def _bool(v):
    if isinstance(v, str) and v.lower() in ("true", "false"): return v.lower() == "true"
    return v

def golden_check(b):
    b = dict(b or {})
    if "first_contact" in b: b["first_contact"] = _bool(b["first_contact"])
    return qa.check(b, log=False)

def summarize(raw_path=RAW, started=None, secs=None, exit_code=None, stderr=""):
    d = json.load(open(raw_path)); res = d.get("results", {})
    rows = res.get("results", []) if isinstance(res, dict) else []
    stats = res.get("stats", {}) if isinstance(res, dict) else {}
    cases = []
    for r in rows:
        tc = r.get("testCase") or {}; ga = r.get("gradingResult") or {}
        cases.append({"id": (r.get("vars") or {}).get("id"), "description": tc.get("description"), "pass": bool(r.get("success")),
                      "verdict": ((r.get("response") or {}).get("output") or {}).get("verdict") if isinstance((r.get("response") or {}).get("output"), dict) else None,
                      "reason": None if r.get("success") else (ga.get("reason") or r.get("error") or "")[:200]})
    p, f = stats.get("successes", sum(c["pass"] for c in cases)), stats.get("failures", sum(not c["pass"] for c in cases))
    errs = stats.get("errors", 0)
    total = p + f + errs
    return {"suite": "qa/golden.yaml", "runner": f"promptfoo ({PROMPTFOO}, node@22 via npx)", "asserts": "deterministic (javascript), no LLM",
            "passed": p, "failed": f, "errors": errs, "total": total, "pass_rate": round(p / total, 3) if total else None,
            "ran_at": started, "duration_sec": secs, "exit_code": exit_code, "cases": cases,
            "failures": [c for c in cases if not c["pass"]], "stderr_tail": stderr[-300:] if exit_code not in (0, 100) else ""}

def run(api="http://127.0.0.1:8810"):
    """Run the golden suite with promptfoo; writes data/qa_reliability.json. Returns the summary."""
    with _run_lock:
        STATE["running"] = True
        started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"); t0 = time.time()
        try:
            if os.path.exists(RAW): os.remove(RAW)
            cmd = ["npx", "-y", "-p", "node@22", "-p", PROMPTFOO, "--", "promptfoo", "eval", "-c", SUITE, "--var", f"run={int(t0)}",
                   "--no-cache", "--no-table", "--no-progress-bar", "--no-write", "-j", "4", "-o", RAW]
            env = {**os.environ, "PROMPTFOO_DISABLE_TELEMETRY": "1", "PROMPTFOO_DISABLE_UPDATE": "1"}
            env.pop("XAI_API_KEY", None)  # deterministic suite never needs a key
            p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=240, env=env)
            secs = round(time.time() - t0, 1)
            if not os.path.exists(RAW):
                s = {"suite": "qa/golden.yaml", "error": "promptfoo produced no results file", "exit_code": p.returncode,
                     "stderr_tail": (p.stderr or p.stdout)[-600:], "ran_at": started, "duration_sec": secs, "pass_rate": None}
            else: s = summarize(RAW, started, secs, p.returncode, p.stderr or "")
        except Exception as e:
            s = {"suite": "qa/golden.yaml", "error": f"{type(e).__name__}: {e}"[:300], "ran_at": started, "pass_rate": None}
        json.dump(s, open(SUMMARY, "w"), indent=1); STATE["running"] = False
        return s

def last():
    try: return {**json.load(open(SUMMARY)), "running": STATE["running"]}
    except Exception: return {"suite": "qa/golden.yaml", "pass_rate": None, "note": "not run yet; POST /api/qa/reliability/run", "running": STATE["running"]}

def register(mcp, lock=None):
    global REGISTERED
    if REGISTERED: return []
    REGISTERED = True
    import asyncio
    @mcp.custom_route("/api/qa/golden-check", methods=["POST"])
    async def api_golden_check(req: Request):
        try: b = await req.json()
        except Exception: b = None
        if not isinstance(b, dict): return JSONResponse({"ok": False, "error": "body must be JSON object"}, status_code=400)
        try: return JSONResponse(await asyncio.to_thread(golden_check, b))
        except ValueError as e: return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    @mcp.custom_route("/api/qa/reliability", methods=["GET"])
    async def api_rel(req: Request): return JSONResponse(last())

    @mcp.custom_route("/api/qa/reliability/run", methods=["POST"])
    async def api_rel_run(req: Request):
        if STATE["running"]: return JSONResponse({"ok": False, "error": "already running"}, status_code=409)
        STATE["running"] = True
        threading.Thread(target=run, daemon=True, name="qa-golden").start()
        return JSONResponse({"ok": True, "status": "started", "poll": "/api/qa/reliability"})

    @mcp.tool(name="qa.reliability")
    async def qa_reliability() -> dict:
        """Last QA-gate golden regression result (promptfoo, deterministic asserts): pass_rate, passed/total, failures, ran_at."""
        return last()
    return ["/api/qa/golden-check", "/api/qa/reliability", "/api/qa/reliability/run", "qa.reliability"]

if __name__ == "__main__":
    print(json.dumps({k: v for k, v in run().items() if k != "cases"}, indent=1))
