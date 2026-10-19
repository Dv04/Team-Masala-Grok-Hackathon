"""T05 (W3): inbound webhooks + task inbox for all 13 depts.
REST:  POST /api/inbound/{dept}      body: hr {job_text|role|resume(s)} | design {brand, brief, caption?} | any dept {title, detail}
       POST /api/tasks               body: {for_dept, title, detail?, source?, parent_id?, priority?}
       GET  /api/tasks?dept=&status= tasks from data/tasks.jsonl (latest state per task)
MCP:   tasks.create, tasks.list, inbound.post
Inbound only writes a *trigger event* on dept from_dept (default pseudo-dept 'inbound'; status done, actor inbound:<src>,
output.kind hire_needed|design_request, for_dept) or, for other depts, a task;
the automation engine's chain rules (lib/chains.py) pick it up and run the dept. No human step."""
import json, os, re, threading
from datetime import datetime, timezone
from starlette.requests import Request
from starlette.responses import JSONResponse
import events

ROOT = os.environ.get("DEPT_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS = f"{ROOT}/data/tasks.jsonl"
# Known dept ids (dev2: sales, support, engineering; dev4: hr, design, ops, qa). The other 6 belong to dev1/dev3,
# so any lowercase slug is accepted as a dept id rather than guessing their names.
KNOWN = ["sales", "support", "engineering", "hr", "design", "ops", "qa"]
SLUG = re.compile(r"^[a-z][a-z0-9_-]{1,30}$")
ALIASES = {"data": "ops", "dataops": "ops", "data-ops": "ops", "qa-gate": "qa"}
_lock = threading.Lock()

def norm_dept(d):
    d = (d or "").strip().lower(); return ALIASES.get(d, d)

def _now(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ---------- task store (records written by W1's actions.create_task, format in INTERFACES.md) ----------
import actions

def list_tasks(dept=None, status=None):
    """Latest state per task from data/tasks.jsonl: {task_id, dept, title, detail, parent_id, created_by, gate, status, ts}.
    status reflects the latest event for that task in the shared log when there is one."""
    latest = {}
    if os.path.exists(TASKS):
        for line in open(TASKS):
            try: r = json.loads(line)
            except Exception: continue
            tid = r.get("task_id") or r.get("id")
            if tid: latest[tid] = {**latest.get(tid, {}), **r}
    if latest:
        evst = {}
        for e in events.read_all():
            if e.get("task_id") in latest: evst[e["task_id"]] = e["status"]
        for tid, t in latest.items():
            if tid in evst: t["status"] = evst[tid]
    out = list(latest.values())
    if dept: out = [t for t in out if t.get("dept") == norm_dept(dept)]
    if status: out = [t for t in out if t.get("status") == status]
    return out

def create_task(for_dept, title, detail="", source="api", parent_id=None, priority="normal", meta=None, actor=None):
    """Task for any dept: actions.create_task (tasks.jsonl + queued event output.kind=task; server fans out to that dept's webhooks)."""
    for_dept = norm_dept(for_dept)
    if not for_dept or not title: raise ValueError("need for_dept and title")
    if not SLUG.match(for_dept): raise ValueError(f"bad dept id '{for_dept}'")
    d = {"text": str(detail)[:1000], "source": source, "priority": priority, **(meta or {})}
    return actions.create_task(for_dept, str(title)[:200], d, parent_id, created_by=str(actor or source)[:60])

# ---------- inbound ----------
def inbound(dept, body, source="webhook"):
    """Turn an external payload into a trigger event. Chain rules start the dept run from it."""
    dept = norm_dept(dept); body = body if isinstance(body, dict) else {}
    src = str(body.get("source") or source)[:40]
    actor = str(body.get("actor") or f"inbound:{src}")[:60]
    tid = events.new_task_id(f"in-{dept}")
    from_dept = norm_dept(body.get("from_dept")) or "inbound"   # e.g. engineering / sales; default pseudo-dept "inbound"
    if from_dept == dept: from_dept = "inbound"
    if dept == "hr":
        role = str(body.get("role") or "Founding support/ops hire")[:120]
        out = {"kind": "hire_needed", "role": role, "job_text": str(body.get("job_text") or "")[:4000],
               "resumes": body.get("resumes") or ([body["resume"]] if body.get("resume") else None), "source": src}
        summary = f"Inbound: hire needed - {role}"
    elif dept == "design":
        out = {"kind": "design_request", "brand": str(body.get("brand") or "Acme Co")[:40],
               "brief": str(body.get("brief") or "Launch visuals")[:400], "source": src}
        if body.get("caption"): out["caption"] = str(body["caption"])[:600]
        summary = f"Inbound: design request for {out['brand']}"
    elif SLUG.match(dept):
        t = create_task(dept, body.get("title") or f"Inbound item for {dept}", body.get("detail") or json.dumps(body)[:800],
                        source=f"inbound:{src}", parent_id=body.get("parent_id"), actor=actor)
        return {"ok": True, "trigger": None, "task": t}
    else:
        raise ValueError(f"bad dept id '{dept}' (lowercase slug, e.g. {KNOWN})")
    out = {k: v for k, v in out.items() if v not in (None, "")}
    out["for_dept"] = dept
    ev = events.emit(from_dept, tid, "done", summary[:200], "live", out, body.get("parent_id"), actor)
    return {"ok": True, "trigger": ev}

# ---------- registration ----------
def register(mcp, lock=None):
    async def _body(req):
        try: return await req.json()
        except Exception: return {}

    @mcp.custom_route("/api/inbound/{dept}", methods=["POST"])
    async def api_inbound(req: Request):
        try: return JSONResponse(inbound(req.path_params["dept"], await _body(req), req.query_params.get("source", "webhook")))
        except ValueError as e: return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    @mcp.custom_route("/api/tasks", methods=["GET", "POST"])
    async def api_tasks(req: Request):
        if req.method == "GET":
            q = req.query_params
            return JSONResponse({"tasks": list_tasks(q.get("dept"), q.get("status"))})
        b = await _body(req) or {}
        try:
            t = create_task(b.get("for_dept") or b.get("dept"), b.get("title"), b.get("detail", ""), b.get("source", "api"),
                            b.get("parent_id"), b.get("priority", "normal"), b.get("meta"), b.get("actor"))
        except ValueError as e: return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
        return JSONResponse({"ok": True, "task": t})

    @mcp.tool(name="tasks.create")
    async def tasks_create(for_dept: str, title: str, detail: str = "", source: str = "mcp", parent_id: str = "", priority: str = "normal") -> dict:
        """Create a task for any of the 13 depts (e.g. sales, support, engineering, hr, design, ops, qa; any dept slug).
        Writes data/tasks.jsonl, logs a queued event on that dept, fires its webhooks. hr/design tasks are auto-run by the engine."""
        return create_task(for_dept, title, detail, source, parent_id or None, priority)

    @mcp.tool(name="tasks.list")
    async def tasks_list(dept: str = "", status: str = "") -> list:
        """List tasks (latest state) for a dept, e.g. dept='support'. status: open|done|failed."""
        return list_tasks(dept or None, status or None)

    @mcp.tool(name="inbound.post")
    async def inbound_post(dept: str, payload: dict, source: str = "mcp") -> dict:
        """Inbound webhook as a tool. dept=hr payload {role, job_text, resumes?} -> HR chain; dept=design payload {brand, brief, caption?} -> Design chain;
        other depts payload {title, detail} -> task. No human step afterwards unless QA routes to the founder."""
        return inbound(dept, payload, source)
    return ["/api/inbound/{dept}", "/api/tasks", "tasks.create", "tasks.list", "inbound.post"]
