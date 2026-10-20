"""Automation engine (T01). events.HOOKS -> enqueue -> one worker thread -> rule table.
Idempotent (data/auto_seen.json), every engine event has actor="auto" + parent_id, chains stop after MAX_HOPS."""
import json, os, queue, threading, traceback
from datetime import datetime
import events

ROOT = os.environ.get("DEPT_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEEN_FILE = f"{ROOT}/data/auto_seen.json"
LOG = f"{ROOT}/logs/auto.log"
MAX_HOPS = 5
RULES = []          # dicts: name, when, then, source, match, handle, once_per_task
_q = queue.Queue()
_seen_lock = threading.Lock()
try: _seen = set(json.load(open(SEEN_FILE)))
except Exception: _seen = set()
_started = False

def log(msg):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f: f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")

def rule(name, when, then, match, handle, source="auto.py", once_per_task=True):
    """Register (or replace, by name) a rule. match(ev)->bool; handle(ev) does the work (may emit events).
    once_per_task: fire at most once per (rule, trigger task_id); else once per trigger event."""
    global RULES
    RULES = [r for r in RULES if r["name"] != name] + [{"name": name, "when": when, "then": then, "source": source,
                                                         "match": match, "handle": handle, "once_per_task": once_per_task}]

def list_rules():
    return [{k: r[k] for k in ("name", "when", "then", "source", "once_per_task")} for r in RULES]

def emit(dept, task_id, status, summary, mode, output=None, parent_id=None, needs_approval=None):
    """Emit an engine event (actor=auto)."""
    return events.emit(dept, task_id, status, summary, mode, output, parent_id, "auto", needs_approval)

def hops(task_id):
    par = {}
    for e in events.read_all():
        if e.get("parent_id") and e["parent_id"] != e["task_id"]: par.setdefault(e["task_id"], e["parent_id"])
    n, t, seen = 0, task_id, set()
    while t in par and t not in seen: seen.add(t); t = par[t]; n += 1
    return n

def _mark(key):
    with _seen_lock:
        if key in _seen: return False
        _seen.add(key)
        json.dump(sorted(_seen), open(SEEN_FILE + ".tmp", "w")); os.replace(SEEN_FILE + ".tmp", SEEN_FILE)
        return True

def _hook(ev): _q.put(ev)   # runs inside the HTTP request: enqueue only

def _process(ev):
    for r in list(RULES):
        try:
            if not r["match"](ev): continue
        except Exception: continue
        key = f"{r['name']}|{ev['task_id']}" if r["once_per_task"] else f"{r['name']}|{ev['task_id']}|{ev['status']}|{ev['ts']}"
        if not _mark(key): log(f"skip dup {key}"); continue
        if hops(ev["task_id"]) >= MAX_HOPS:
            log(f"hop guard stop {key}"); emit(ev["dept"], ev["task_id"], "failed", f"Automation stopped: chain > {MAX_HOPS} hops",
                                             ev.get("mode", "live"), {"rule": r["name"], "reason": "hop_guard"}, ev.get("parent_id")); continue
        log(f"fire {r['name']} on {ev['dept']}/{ev['task_id']}/{ev['status']}")
        try: r["handle"](ev)
        except Exception as e:
            log(f"ERROR {r['name']}: {traceback.format_exc()[-800:]}")
            try: emit(ev["dept"], ev["task_id"], "failed", f"Automation rule {r['name']} errored: {type(e).__name__}",
                      ev.get("mode", "live"), {"rule": r["name"], "error": str(e)[:300]}, ev.get("parent_id"))
            except Exception: pass

def _worker():
    while True:
        ev = _q.get()
        try: _process(ev)
        except Exception: log("worker error " + traceback.format_exc()[-500:])

def start():
    global _started
    if _started: return
    _started = True
    events.HOOKS.append(_hook)
    threading.Thread(target=_worker, daemon=True, name="auto-worker").start()
    log(f"engine started with {len(RULES)} rules")

def drain(timeout=10):
    """Test helper: wait until the queue is empty."""
    import time; t = time.time()
    while not _q.empty() and time.time() - t < timeout: time.sleep(0.05)
