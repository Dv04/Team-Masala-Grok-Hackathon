"""Shared event log for Team Masala departments (contract section 1).
Stdlib only, so any dept script can `import events` or use bin/emit.
"""
import fcntl, json, os, re, uuid
from datetime import datetime, timezone

LOG = os.environ.get("EVENTS_LOG", os.path.join(os.environ.get("DEPT_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "events.jsonl"))
STATUSES = {"queued", "running", "needs_approval", "approved", "rejected", "done", "failed"}
MODES = {"live", "mock"}
HOOKS = []  # callables run after each append (e.g. webhook fan-out)
REQUIRED = ("ts", "dept", "task_id", "status", "summary", "mode")
ALLOWED = set(REQUIRED) | {"parent_id", "actor", "output", "needs_approval"}
SECRET_RE = re.compile(r"(xai-[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,})")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def new_task_id(prefix="t"):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def validate(ev):
    """Return a normalized event dict or raise ValueError."""
    if not isinstance(ev, dict):
        raise ValueError("event must be a JSON object")
    ev = dict(ev)
    ev.setdefault("ts", now_iso())
    ev.setdefault("output", {})
    ev.setdefault("needs_approval", ev.get("status") == "needs_approval")
    missing = [k for k in REQUIRED if not ev.get(k)]
    if missing:
        raise ValueError(f"missing required fields: {missing}")
    extra = set(ev) - ALLOWED
    if extra:
        raise ValueError(f"unknown fields: {sorted(extra)} (put dept-specific data in 'output')")
    if ev["status"] not in STATUSES:
        raise ValueError(f"status must be one of {sorted(STATUSES)}")
    if ev["mode"] not in MODES:
        raise ValueError("mode must be 'live' or 'mock' (honest; mock is never shown as live)")
    if not isinstance(ev["needs_approval"], bool):
        raise ValueError("needs_approval must be boolean")
    try:
        datetime.fromisoformat(ev["ts"].replace("Z", "+00:00"))
    except Exception:
        raise ValueError("ts must be ISO 8601, e.g. 2026-10-19T23:30:00Z")
    for k in ("dept", "task_id", "summary"):
        if not isinstance(ev[k], str):
            raise ValueError(f"{k} must be a string")
    ev["dept"] = ev["dept"].strip().lower()
    blob = json.dumps(ev)
    if SECRET_RE.search(blob):
        raise ValueError("event appears to contain a secret/API key; refusing to log it")
    return ev


def append(ev, path=None):
    ev = validate(ev)
    path = path or LOG
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = json.dumps(ev, separators=(",", ":"), ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(line)
        f.flush()
        fcntl.flock(f, fcntl.LOCK_UN)
    for h in HOOKS:
        try: h(ev)
        except Exception: pass
    return ev


def emit(dept, task_id, status, summary, mode, output=None, parent_id=None, actor=None, needs_approval=None):
    ev = {"dept": dept, "task_id": task_id, "status": status, "summary": summary, "mode": mode,
          "output": output or {}}
    if parent_id: ev["parent_id"] = parent_id
    if actor: ev["actor"] = actor
    if needs_approval is not None: ev["needs_approval"] = needs_approval
    return append(ev)


def read_all(path=None):
    path = path or LOG
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try: out.append(json.loads(line))
                except json.JSONDecodeError: pass
    return out
