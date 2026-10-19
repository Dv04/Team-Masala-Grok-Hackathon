"""T04 (W3): cross-dept chain rules added to the automation engine (lib/auto.py).
Chains 1+2 (hire_needed->HR, design_request->Design) are built in (lib/flows.py); this module adds:
  chain.needs_qa->qa     any dept (all 13, incl. dev2's sales/support/engineering) posts output.needs_qa:true + kind + content
                         -> qa.check (verdict event on dept qa with for_dept -> server fans out to that dept's webhooks)
                         -> pass: source task 'done' (cleared to send) | founder: stays in founder queue | fail: 'running' revise request
  chain.ops_task->dept   queued task (output.kind=task, e.g. from an ops scan) -> hr/design with auto_run: re-run the dept;
                         any other dept: routed (webhook fan-out by server) + ops 'done' routing record."""
import json, os
import events, auto, qa, depts

ROOT = os.environ.get("DEPT_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNABLE = {"hr", "design"}

def _out(ev): return ev.get("output") or {}

# ---- chain 3: QA for every dept
def _needs_qa(ev):
    o = _out(ev); dept, tid = ev["dept"], ev["task_id"]
    content = o.get("content")
    if not isinstance(content, str): content = json.dumps(content)
    r = qa.check({"dept": dept, "task_id": tid, "kind": str(o.get("kind")), "content": content,
                  "context": str(o.get("context") or ""), "parent_id": ev.get("parent_id"),
                  **({"first_contact": o["first_contact"]} if "first_contact" in o else {})})
    v = r["verdict"]; base = {"kind": "qa_result", "qa": {"verdict": v, "score": r["score"], "reasons": r["reasons"][:4]},
                              "checked_kind": o.get("kind")}
    if v == "pass":
        auto.emit(dept, tid, "done", f"{dept}: QA pass, cleared to send ({o.get('kind')})", ev.get("mode", "live"), base, ev.get("parent_id"))
    elif v == "fail":
        auto.emit(dept, tid, "running", f"{dept}: QA fail, revise and resubmit with needs_qa:true", ev.get("mode", "live"),
                  {**base, "next": "revise once; a 2nd fail on this task goes to the founder"}, ev.get("parent_id"))
    # founder: qa.check already logged needs_approval on this task -> founder queue; approve/reject fans out to the dept
auto.rule("chain.needs_qa->qa", "any dept event with output.needs_qa:true + output.kind + output.content (all 13 depts)",
          "qa.check -> verdict webhook to that dept; pass: task done, fail: revise request, founder: approval queue",
          lambda ev: _out(ev).get("needs_qa") is True and ev.get("dept") != "qa" and _out(ev).get("kind") and "content" in _out(ev),
          _needs_qa, "chains.py", once_per_task=False)

# ---- chain 4: ops task -> target dept
def _first_with(task_id, key):
    for e in events.read_all():
        if e.get("task_id") == task_id and key in _out(e): return e
    return None

def _ops_task(ev):
    o = _out(ev); d = o.get("detail") if isinstance(o.get("detail"), dict) else {}
    dept, tid = ev["dept"], ev["task_id"]
    if dept in RUNNABLE and d.get("auto_run"):
        stuck = d.get("stuck_task")
        if dept == "design":
            src = _first_with(stuck, "brand") if stuck else None; so = _out(src) if src else {}
            r = depts.design_run({"task_id": events.new_task_id("design"), "parent_id": tid, "actor": "auto",
                                  "brand": so.get("brand") or d.get("brand"), "brief": d.get("brief") or d.get("text"), "n_posts": 1})
        else:
            r = depts.hr_run({"task_id": events.new_task_id("hr"), "parent_id": tid, "actor": "auto", "job_text": d.get("job_text", "")})
        if stuck:
            auto.emit(dept, stuck, "done", f"{dept}: stuck task superseded by re-run {r.get('task_id')}", ev.get("mode", "live"),
                      {"superseded_by": r.get("task_id"), "via_task": tid}, ev.get("parent_id"))
        auto.emit(dept, tid, "done", f"{dept}: ops task executed (re-run {r.get('task_id')} -> {r.get('status')})", ev.get("mode", "live"),
                  {"rerun_task": r.get("task_id"), "rerun_status": r.get("status")}, ev.get("parent_id"))
        return
    try: n = sum(1 for h in json.load(open(f"{ROOT}/data/webhooks.json")) if h.get("dept") in (dept, "all"))
    except Exception: n = 0
    auto.emit("ops", events.new_task_id("ops-route"), "done", f"Ops: task {tid} routed to {dept} ({n} webhook(s))", "live",
              {"kind": "task_routed", "for_dept": dept, "task": tid, "webhooks": n,
               "pull": f"GET /api/tasks?dept={dept}"}, tid)
auto.rule("chain.ops_task->dept", "queued task event (output.kind=task) for any dept, e.g. created by an ops scan",
          "hr/design with auto_run: re-run the dept (stuck task superseded); others: webhook fan-out + routing record on ops",
          lambda ev: ev.get("status") == "queued" and _out(ev).get("kind") == "task", _ops_task, "chains.py")

def register(mcp=None, lock=None):
    return ["chain.needs_qa->qa", "chain.ops_task->dept"]
