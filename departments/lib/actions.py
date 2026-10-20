"""Action executors (T02): real side effects on the box. Sandbox only: emails go to data/outbox as .eml files
with fictional recipients (example.com, RFC 2606). Mock-mode files carry .MOCK in their names."""
import json, os, shutil, threading, fcntl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
import events

ROOT = os.environ.get("DEPT_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTBOX, PUBLISHED = f"{ROOT}/data/outbox", f"{ROOT}/data/published"
ATS, TASKS = f"{ROOT}/data/hr/pipeline.json", f"{ROOT}/data/tasks.jsonl"
SANDBOX_DOMAIN = "example.com"  # reserved, never a real inbox
_lock = threading.Lock()

def _now(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def _safe(s): return "".join(c for c in str(s) if c.isalnum() or c in "-_.")[:80] or "x"

def done(dept, task_id, summary, mode, action, extra=None, parent_id=None, actor="auto"):
    out = dict(extra or {}); out["action"] = action
    return events.emit(dept, task_id, "done", summary[:200], mode, out, parent_id, actor)

def outbox_email(task_id, to_name, subject, body, mode, executed_by="auto"):
    os.makedirs(OUTBOX, exist_ok=True)
    to = f"{_safe(to_name).lower()}@candidates.{SANDBOX_DOMAIN}"
    m = EmailMessage()
    m["From"] = f"Founder (sandbox) <founder@company.{SANDBOX_DOMAIN}>"; m["To"] = to
    m["Subject"] = ("[MOCK] " if mode == "mock" else "") + (subject or "(no subject)")
    m["Date"] = formatdate(localtime=True); m["Message-ID"] = make_msgid(domain=f"company.{SANDBOX_DOMAIN}")
    m["X-Sandbox"] = "true; not delivered; fictional recipient"; m["X-Mode"] = mode; m["X-Executed-By"] = executed_by
    m.set_content(body or "")
    path = f"{OUTBOX}/{_safe(task_id)}{'.MOCK' if mode == 'mock' else ''}.eml"
    open(path, "w").write(m.as_string())
    return {"type": "email_outbox", "path": path, "url": "/files/outbox/" + os.path.basename(path),
            "to": to, "executed_by": executed_by, "sandbox": True}

def publish_design(task_id, assets, caption, brand, mode, executed_by="auto"):
    d = f"{PUBLISHED}/{_safe(task_id)}"; os.makedirs(d, exist_ok=True)
    files = []
    for a in assets or []:
        f = a.get("file")
        if f and os.path.isfile(f):
            dst = os.path.join(d, os.path.basename(f)); shutil.copyfile(f, dst); files.append(os.path.basename(dst))
    cap = f"{d}/caption.json"
    json.dump({"task_id": task_id, "brand": brand, "caption": caption, "mode": mode, "files": files,
               "published_at": _now(), "executed_by": executed_by,
               "note": "MOCK placeholders, not AI generated" if mode == "mock" else "generated via Grok-MCP"},
              open(cap, "w"), indent=1)
    return {"type": "design_publish", "path": cap, "url": f"/files/published/{_safe(task_id)}/caption.json",
            "files": [f"/files/published/{_safe(task_id)}/{x}" for x in files], "executed_by": executed_by}

def ats_update(task_id, shortlist, stage, executed_by="auto", note=""):
    with _lock:
        try: db = json.load(open(ATS))
        except Exception: db = {"candidates": {}, "history": []}
        ids = []
        for c in shortlist or []:
            cid = str(c.get("candidate_id") or "unknown"); ids.append(cid)
            rec = db["candidates"].setdefault(f"{task_id}:{cid}", {"candidate_id": cid, "initials": c.get("initials")})
            rec.update({"stage": stage, "task_id": task_id, "updated": _now()})
        db["history"].append({"ts": _now(), "task_id": task_id, "stage": stage, "candidates": ids, "by": executed_by, "note": note[:300]})
        os.makedirs(os.path.dirname(ATS), exist_ok=True)
        json.dump(db, open(ATS + ".tmp", "w"), indent=1); os.replace(ATS + ".tmp", ATS)
    return {"type": "ats_update", "path": ATS, "stage": stage, "candidates": ids, "executed_by": executed_by}

def create_task(for_dept, title, detail=None, parent_id=None, created_by="auto", mode="live", gate="internal"):
    """Append a task to data/tasks.jsonl and emit a `queued` event (output.kind=task) for that dept.
    server.py fans that event out to the dept's registered webhooks."""
    tid = events.new_task_id(_safe(for_dept)[:12] or "task")
    rec = {"task_id": tid, "dept": for_dept.lower(), "title": title[:200], "detail": detail or {}, "parent_id": parent_id,
           "created_by": created_by, "gate": gate, "status": "queued", "ts": _now()}
    with open(TASKS, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX); f.write(json.dumps(rec) + "\n"); fcntl.flock(f, fcntl.LOCK_UN)
    events.emit(for_dept.lower(), tid, "queued", f"Task: {title}"[:200], mode,
                {"kind": "task", "title": title[:200], "detail": detail or {},
                 "action": {"type": "task_created", "path": TASKS, "executed_by": created_by}}, parent_id, "auto")
    return rec
