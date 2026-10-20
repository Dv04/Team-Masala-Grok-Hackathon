"""Built-in automation rules (W1): chain 1 (hire_needed->HR), chain 2 (design_request->Design),
pass-path executors, founder approve->execute, founder reject->revise once->2nd reject failed.
W3's lib/chains.py may add more rules or replace these by name via auto.rule(...)."""
import events, auto, actions, depts

def _out(ev): return ev.get("output") or {}
def _last_src(task_id, dept):
    """Latest dept event for the task carrying the work product (not founder/qa/action events)."""
    for e in reversed(events.read_all()):
        o = e.get("output") or {}
        if e.get("task_id") == task_id and e.get("dept") == dept and e.get("actor") != "founder" and \
           "action" not in o and ("outreach_draft" in o or "assets" in o):
            return e
    return None
def _founder_rejects(task_id):
    return sum(1 for e in events.read_all() if e.get("task_id") == task_id and e.get("actor") == "founder" and e.get("status") == "rejected")
def _trigger_root(ev): return ev.get("parent_id") or ev["task_id"]

# ---- chain 1: hire_needed -> HR
def _hire(ev):
    o = _out(ev)
    depts.hr_run({"task_id": events.new_task_id("hr"), "parent_id": ev["task_id"], "actor": "auto", "write_jd": True,
                  "role": o.get("role") or "Founding Support & Ops Lead", "blind": bool(o.get("blind", True)),
                  "job_text": o.get("job_text") or "", "top_k": int(o.get("top_k", 3))})
auto.rule("chain.hire_needed->hr", "any dept event with output.kind=hire_needed (e.g. engineering)",
          "HR ranks candidates + drafts outreach -> QA outbound_email -> founder (first contact) or pass-path send",
          lambda ev: _out(ev).get("kind") == "hire_needed" and ev.get("dept") != "hr" and ev.get("status") != "failed", _hire, "flows.py")

# ---- chain 2: design_request -> Design
def _design(ev):
    o = _out(ev)
    depts.design_run({"task_id": events.new_task_id("design"), "parent_id": ev["task_id"], "actor": "auto",
                      "brand": o.get("brand"), "brief": o.get("brief"), "caption": o.get("caption"),
                      "n_posts": int(o.get("n_posts", 2))})
auto.rule("chain.design_request->design", "any non-design dept event with output.kind=design_request (sales/marketing/support)",
          "Design builds brand kit + caption -> QA public_post (fail: revise once) -> pass: auto-publish",
          lambda ev: _out(ev).get("kind") == "design_request" and ev.get("dept") != "design" and ev.get("status") != "failed", _design, "flows.py")

# ---- executors
def _exec_hr(src, executed_by, note=""):
    o = _out(src); d = o.get("outreach_draft") or {}; sl = o.get("shortlist") or []
    top = sl[0] if sl else {}
    who = top.get("initials") or top.get("candidate_id") or "candidate"
    a1 = actions.outbox_email(src["task_id"], f"{who}-{top.get('candidate_id','c')}", d.get("subject"), d.get("body"), src["mode"], executed_by)
    a2 = actions.ats_update(src["task_id"], sl[:1], "contacted", executed_by, note)
    extra = {"kind": "outbound_email", "ats": a2}
    if executed_by == "founder":  # X01: founder approved this hire's outreach -> draft 30/60/90 onboarding plan
        import hr_extras
        ob = hr_extras.onboarding_plan(src["task_id"], o.get("role"), top, src["mode"]); ob["executed_by"] = executed_by
        ob["url"] = "/files/onboarding/" + ob["path"].rsplit("/", 1)[-1]; extra["onboarding"] = ob
    actions.done("hr", src["task_id"], f"HR: outreach sent to sandbox outbox + ATS contacted ({executed_by})", src["mode"],
                 a1, extra, src.get("parent_id"))

def _exec_design(src, executed_by):
    o = _out(src)
    a = actions.publish_design(src["task_id"], o.get("assets"), o.get("caption"), o.get("brand"), src["mode"], executed_by)
    actions.done("design", src["task_id"], f"Design: published {len(a['files'])} assets + caption ({executed_by})", src["mode"],
                 a, {"kind": "public_post"}, src.get("parent_id"))

_is_product = lambda ev: "action" not in _out(ev) and ev.get("actor") != "founder"
auto.rule("exec.hr_on_pass", "hr done event with outreach_draft (QA pass, e.g. follow-up)", "write .eml to data/outbox + ATS stage contacted",
          lambda ev: ev["dept"] == "hr" and ev["status"] == "done" and "outreach_draft" in _out(ev) and _is_product(ev),
          lambda ev: _exec_hr(ev, "auto"), "flows.py")
auto.rule("exec.design_on_pass", "design done event with assets (QA pass)", "copy assets + caption.json to data/published/<task>/",
          lambda ev: ev["dept"] == "design" and ev["status"] == "done" and "assets" in _out(ev) and _is_product(ev),
          lambda ev: _exec_design(ev, "auto"), "flows.py")

# ---- founder approve -> execute
def _approved(ev):
    src = _last_src(ev["task_id"], ev["dept"])
    if not src: return
    note = _out(ev).get("note", "")
    _exec_hr(src, "founder", note) if ev["dept"] == "hr" else _exec_design(src, "founder")
auto.rule("founder.approve->execute", "founder approved an hr/design task", "run the same executor (outbox+ATS / publish), executed_by=founder",
          lambda ev: ev.get("actor") == "founder" and ev["status"] == "approved" and ev["dept"] in ("hr", "design"),
          _approved, "flows.py", once_per_task=False)

# ---- founder reject -> revise once -> 2nd reject failed
def _rejected(ev):
    src = _last_src(ev["task_id"], ev["dept"]); note = _out(ev).get("note", "") or "founder rejected"
    n = _founder_rejects(ev["task_id"])
    if ev["dept"] == "hr" and src:
        actions.ats_update(ev["task_id"], (_out(src).get("shortlist") or [])[:1], "rejected", "founder", note)
    if n >= 2 or not src:
        auto.emit(ev["dept"], ev["task_id"], "failed", f"{ev['dept']}: stopped after founder reject #{n}", ev.get("mode", "mock"),
                  {"reason": "second founder reject" if n >= 2 else "nothing to revise", "note": note[:300]}, ev.get("parent_id"))
        return
    auto.emit(ev["dept"], ev["task_id"], "running", f"{ev['dept']}: revising once with founder note", src["mode"],
              {"revision_note": note[:300]}, src.get("parent_id"))
    if ev["dept"] == "hr":
        depts.hr_run({"task_id": ev["task_id"], "parent_id": src.get("parent_id"), "actor": "auto", "revision_note": note, "revision": n})
    else:
        o = _out(src)
        depts.design_run({"task_id": ev["task_id"], "parent_id": src.get("parent_id"), "actor": "auto", "brand": o.get("brand"),
                          "brief": note, "revision_note": note, "n_posts": max(0, len(o.get("assets") or []) - 1)})
auto.rule("founder.reject->revise_once", "founder rejected an hr/design task", "1st reject: log (+ATS rejected), revise once with the note -> QA again; 2nd reject: failed",
          lambda ev: ev.get("actor") == "founder" and ev["status"] == "rejected" and ev["dept"] in ("hr", "design"),
          _rejected, "flows.py", once_per_task=False)
