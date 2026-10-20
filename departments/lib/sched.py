"""T06 (W3): Data/ops scheduler. Every OPS_SCAN_SEC (default 60 s) a thread runs DuckDB anomaly SQL over the shared
event log and turns each *new* anomaly into a task for the responsible dept (lib/inbound.create_task: tasks.jsonl +
queued event on that dept + its webhooks). Dedupe: data/ops_anomalies.json keeps every anomaly key ever acted on.
Also exposed as MCP tool ops.scan and REST POST /api/ops/scan (a Grok Bot routine can call either; pass actor).
Anomaly rules (SQL in RULES):
  approval_waiting  latest status needs_approval for > OPS_APPROVAL_MIN (10) min  -> task "nudge founder" for that dept
  stuck_running     latest status running for > OPS_RUNNING_MIN (5) min           -> task "re-queue" (auto_run) for that dept
  fail_rate         dept with >= 3 tasks and > 30% latest-failed                   -> task "investigate failures" for that dept
Tasks created by ops are internal: they pass the QA gate (kind internal) and the verdict is logged."""
import fcntl, json, os, threading, time
import duckdb
from starlette.requests import Request
from starlette.responses import JSONResponse
import events, ops, qa, inbound

ROOT = os.environ.get("DEPT_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEEN = f"{ROOT}/data/ops_anomalies.json"
INTERVAL = int(os.environ.get("OPS_SCAN_SEC", "60"))
APPROVAL_MIN = int(os.environ.get("OPS_APPROVAL_MIN", "10"))
RUNNING_MIN = int(os.environ.get("OPS_RUNNING_MIN", "5"))
_scan_lock = threading.Lock()
_started = False
STATE = {"last_scan": None, "scans": 0, "interval_sec": INTERVAL}

_LATEST = """
  l AS (SELECT task_id, arg_max(status, ts) AS status, arg_max(summary, ts) AS summary, max(ts) AS since
        FROM events WHERE dept <> 'founder' GROUP BY task_id),
  d AS (SELECT task_id, arg_max(dept, ts) AS dept FROM events WHERE dept NOT IN ('qa','founder') GROUP BY task_id)"""
RULES = {
 "approval_waiting": f"""WITH {_LATEST}
  SELECT l.task_id, coalesce(d.dept,'qa') AS dept, l.summary, round((epoch(now())-epoch(l.since))/60,1) AS minutes
  FROM l LEFT JOIN d USING (task_id) WHERE l.status='needs_approval' AND l.since < now() - INTERVAL {APPROVAL_MIN} MINUTE""",
 "stuck_running": f"""WITH {_LATEST}
  SELECT l.task_id, coalesce(d.dept,'qa') AS dept, l.summary, round((epoch(now())-epoch(l.since))/60,1) AS minutes
  FROM l LEFT JOIN d USING (task_id) WHERE l.status='running' AND l.since < now() - INTERVAL {RUNNING_MIN} MINUTE""",
 "fail_rate": """WITH t AS (SELECT dept, task_id, arg_max(status, ts) AS status FROM events
                   WHERE dept NOT IN ('qa','founder','ops') GROUP BY dept, task_id)
  SELECT dept, count(*) AS tasks, round(avg(CASE WHEN status='failed' THEN 1 ELSE 0 END),2) AS fail_rate
  FROM t GROUP BY dept HAVING count(*) >= 3 AND avg(CASE WHEN status='failed' THEN 1 ELSE 0 END) > 0.3""",
}

def _rows(con, sql):
    cur = con.execute(sql); cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

def _load_seen():
    try: return set(json.load(open(SEEN)))
    except Exception: return set()

def _save_seen(s):
    tmp = SEEN + ".tmp"; json.dump(sorted(s), open(tmp, "w")); os.replace(tmp, SEEN)

def find_anomalies(path=None):
    path = path or events.LOG
    if not os.path.exists(path) or os.path.getsize(path) == 0: return []
    con = duckdb.connect()
    try:
        con.execute(ops.view_sql(path)); out = []
        for rule, sql in RULES.items():
            for r in _rows(con, sql):
                key = f"{rule}:{r.get('task_id') or r['dept']}"
                out.append({"rule": rule, "key": key, **{k: (float(v) if isinstance(v, (int, float)) and k != 'tasks' else v) for k, v in r.items()}})
        return out
    finally: con.close()

def _task_for(a):
    if a["rule"] == "approval_waiting":
        return (a["dept"], f"Nudge founder: approval waiting {a['minutes']} min ({a['task_id']})",
                f"'{a['summary']}' has waited {a['minutes']} min in the founder queue. Ping the founder or send a holding reply.",
                {"anomaly": a, "auto_run": False, "stuck_task": a["task_id"]})
    if a["rule"] == "stuck_running":
        return (a["dept"], f"Re-queue stuck task {a['task_id']} (running {a['minutes']} min)",
                f"'{a['summary']}' has been running {a['minutes']} min with no update. Re-run it.",
                {"anomaly": a, "auto_run": True, "stuck_task": a["task_id"]})
    return (a["dept"], f"Investigate failures in {a['dept']} ({int(a['fail_rate']*100)}% of {a['tasks']} tasks failed)",
            "Failure rate above 30%. Check inputs / QA reasons and fix the cause.", {"anomaly": a, "auto_run": False})

def scan(actor="ops-scheduler", log_empty=True):
    """One scan. Creates exactly one task per new anomaly (deduped forever by key) and logs one ops event.
    Returns {scan_id, anomalies, new, tasks_created}."""
    with _scan_lock:
        STATE["last_scan"] = events.now_iso(); STATE["scans"] += 1
        found = find_anomalies(); seen = _load_seen()
        new = [a for a in found if a["key"] not in seen]
        sid = events.new_task_id("ops-scan"); created = []
        for a in new:
            dept, title, detail, meta = _task_for(a)
            q = qa.check({"dept": "ops", "task_id": sid, "kind": "internal", "content": f"{title}. {detail}"}, log=False)
            t = inbound.create_task(dept, title, detail, source="ops-scan", parent_id=sid, meta={**meta, "qa": q["verdict"]},
                                    actor=actor)
            created.append({"task_id": t["task_id"], "for_dept": dept, "rule": a["rule"], "qa": q["verdict"]})
            seen.add(a["key"])
        if new: _save_seen(seen)
        res = {"scan_id": sid, "anomalies": len(found), "new": len(new), "tasks_created": created, "actor": actor}
        if new or log_empty:
            events.emit("ops", sid, "done", f"Ops scan: {len(found)} anomalies, {len(created)} new task(s)", "live",
                        {"kind": "ops_scan", "anomalies": found[:20], "tasks_created": created,
                         "rules": list(RULES), "action": {"type": "task", "path": "data/tasks.jsonl", "executed_by": "auto"} if created else None},
                        None, actor)
        return res

def _loop():
    while True:
        time.sleep(INTERVAL)
        try: scan("ops-scheduler", log_empty=False)   # silent unless something new, keeps the feed readable
        except Exception as e:
            try: open(f"{ROOT}/logs/sched.log", "a").write(f"{events.now_iso()} scan error {type(e).__name__}: {e}\n")
            except Exception: pass

def start():
    global _started
    if _started or os.environ.get("OPS_SCHED", "1") == "0": return False
    _started = True; threading.Thread(target=_loop, daemon=True, name="ops-scheduler").start(); return True

def register(mcp, lock=None):
    @mcp.custom_route("/api/ops/scan", methods=["POST", "GET"])
    async def api_scan(req: Request):
        import asyncio
        if req.method == "GET":
            return JSONResponse({**STATE, "rules": RULES, "anomalies_now": await asyncio.to_thread(find_anomalies)})
        try: b = await req.json()
        except Exception: b = {}
        return JSONResponse(await asyncio.to_thread(scan, str((b or {}).get("actor") or "ops-api")[:60]))

    @mcp.tool(name="ops.scan")
    async def ops_scan(actor: str = "mcp") -> dict:
        """Data/ops anomaly scan over the shared event log (DuckDB): approvals waiting >10 min, tasks running >5 min,
        dept failure rate >30%. Each new anomaly becomes one task for the responsible dept (deduped). Pass actor='grok-routine' from routines."""
        import asyncio
        return await asyncio.to_thread(scan, actor or "mcp")
    start()
    return ["/api/ops/scan", "ops.scan", "thread:ops-scheduler"]
