"""Pulse Studio stand-ins (dev4) for teammates' departments, so the full demo chain works even if their code hasn't landed.
STANDINS=1 (default on) | STANDIN_WAIT=8 sec | STANDIN_STALL=30 sec. Each stand-in waits; if the real dept already emitted
an event for that step (any event from that dept, actor != standin-dev4, referencing the trigger task), it does nothing.
Every stand-in event: actor 'standin-dev4', output.standin=true, mode mock. Nothing is ever posted or sent externally.
  research      trend_spotted -> trend_accepted
  legal         trend_spotted -> trademark/offensive pre-check + qa.check -> legal_precheck
  engineering, sales  listing_live -> listing_live (url /files/published/<task>/index.html)
  marketing     listing_live -> 3 MOCK post drafts in data/published/<task>/posts.md (never posted)
  support       listing_live -> one canned buyer Q&A through QA (needs_qa chain)
  finance       order_placed -> margin_update (computed_by finance-standin)
  integrations  trend_spotted -> chain_stalled if no listing_live / blocked / founder step after STANDIN_STALL sec"""
import json, os, threading
import events, auto, qa, pulse

ON = os.environ.get("STANDINS", "1") == "1"
WAIT = float(os.environ.get("STANDIN_WAIT", "8")); STALL = float(os.environ.get("STANDIN_STALL", "30"))
ACTOR = "standin-dev4"

def _out(ev): return ev.get("output") or {}
def _real(dept, ref):
    for e in events.read_all():
        if (e.get("output") or {}).get("kind") == "trend_spotted" and e.get("task_id") == ref: continue  # the trigger itself
        if e.get("dept") == dept and e.get("actor") != ACTOR and (e.get("parent_id") == ref or e.get("task_id") == ref or ref in json.dumps(e.get("output") or {})):
            return True
    return False
def _emit(dept, status, summary, output, parent, tid=None):
    return events.emit(dept, tid or events.new_task_id(dept[:6] + "-si"), status, f"[STAND-IN] {summary}"[:200], "mock",
                       {**output, "standin": True, "standin_note": "dev4 stand-in until the real dept bot is connected"}, parent, ACTOR)
def _later(sec, dept, ref, fn):
    def go():
        try:
            if not _real(dept, ref): fn()
            else: auto.log(f"standin {dept} skipped: real event for {ref}")
        except Exception as e: auto.log(f"standin {dept} error {type(e).__name__}: {e}")
    t = threading.Timer(sec, go); t.daemon = True; t.start()

def _trend(ev):
    tid, o = ev["task_id"], _out(ev)
    _later(WAIT, "research", tid, lambda: _emit("research", "done", f"Research: trend accepted '{o.get('trend')}'",
                                                {"kind": "trend_accepted", "trend": o.get("trend"), "source": o.get("source")}, tid))
    def legal():
        hard, _, _ = pulse.product_rules({"trend": o.get("trend"), "title": o.get("trend"), "price_usd": 10, "cost_usd": 1})
        lt = events.new_task_id("legal-si")
        r = qa.check({"dept": "legal", "task_id": lt, "kind": "internal", "content": f"Trend pre-check: {o.get('trend')}", "parent_id": tid, "mode": "mock"})
        v = "fail" if hard else r["verdict"]
        _emit("legal", "done" if v == "pass" else "failed", f"Legal pre-check {v}: '{o.get('trend')}'",
              {"kind": "legal_precheck", "verdict": v, "reasons": (hard or r["reasons"])[:4], "trend_task": tid}, tid, lt)
    _later(WAIT, "legal", tid, legal)
    def stall():
        kids = [e for e in events.read_all() if e.get("parent_id") == tid]
        done = any(_out(e).get("kind") in ("listing_live", "product_blocked") or e.get("status") == "needs_approval" for e in kids)
        if not done:
            _emit("integrations", "failed", f"Integrations: chain stalled for trend task {tid} (> {int(STALL)}s, no listing/blocked/founder step)",
                  {"kind": "chain_stalled", "task": tid, "waited_sec": STALL, "steps_seen": [_out(e).get("kind") for e in kids]}, tid)
    _later(STALL, "integrations", tid, stall)

def _listing(ev):
    tid, o = ev["task_id"], _out(ev); p = o.get("product") or {}; url = o.get("url") or f"/files/published/{tid}/index.html"
    for d in ("engineering", "sales"):
        _later(WAIT, d, tid, lambda d=d: _emit(d, "done", f"{d.title()}: listing live at {url}",
                                               {"kind": "listing_live", "url": url, "listing_task": tid, "product": p}, tid))
    def mkt():
        path = f"{pulse.PUB}/{pulse._safe(tid)}/posts.md"
        posts = [f"New drop: {p.get('title')} {p.get('product_type')}. {p.get('tagline')} ${p.get('price_usd')}",
                 f"Everyone's talking about {p.get('trend')}. We made it wearable/stickable. Link in bio.",
                 f"Limited run: {p.get('title')}. Printed on demand, ships fast."]
        open(path, "w").write("# MOCK post drafts (never posted; founder must approve any real post)\n\n" + "\n".join(f"{i+1}. {x}" for i, x in enumerate(posts)) + "\n")
        _emit("marketing", "done", f"Marketing: 3 post drafts for {p.get('title')} (MOCK, not posted)",
              {"kind": "posts_drafted", "path": path, "url": f"/files/published/{pulse._safe(tid)}/posts.md", "posts": posts, "posted": False}, tid)
    _later(WAIT, "marketing", tid, mkt)
    _later(WAIT, "support", tid, lambda: _emit("support", "running", f"Support: canned buyer Q&A for {p.get('title')}",
        {"kind": "customer_reply", "needs_qa": True, "question": "When will my order ship?",
         "content": f"Thanks for ordering {p.get('title')}! It's printed on demand and usually ships in 3-5 business days.",
         "context": "Buyer asked about shipping time for a print-on-demand item.", "listing_task": tid}, tid))

def _order(ev):
    oid, o = ev["task_id"], _out(ev)
    def fin():
        rev, cost = float(o.get("revenue_usd") or 0), float(o.get("cost_usd") or 0); t = pulse.totals()
        _emit("finance", "done", f"Finance: margin on {oid} ${rev - cost:.2f} ({round((rev - cost) / rev * 100, 1) if rev else 0}%)",
              {"kind": "margin_update", "computed_by": "finance-standin", "order_id": oid, "revenue_usd": rev, "cost_usd": cost,
               "margin_pct": round((rev - cost) / rev * 100, 1) if rev else None, "totals": t}, oid)
    _later(WAIT, "finance", oid, fin)

if ON:
    real = lambda ev: ev.get("actor") != ACTOR
    auto.rule("standin.trend", "trend_spotted (Pulse Studio)", f"after {WAIT:g}s, if the real dept hasn't: research accept, legal pre-check; integrations chain_stalled after {STALL:g}s",
              lambda ev: real(ev) and _out(ev).get("kind") == "trend_spotted" and ev.get("dept") not in pulse.SKIP_DEPTS, _trend, "standins.py")
    auto.rule("standin.listing", "design listing_live", f"after {WAIT:g}s, if missing: engineering+sales listing_live, marketing MOCK posts, support Q&A via QA",
              lambda ev: real(ev) and ev.get("dept") == "design" and _out(ev).get("kind") == "listing_live", _listing, "standins.py")
    auto.rule("standin.order", "ops order_placed", f"after {WAIT:g}s, if dev3 finance hasn't: margin_update (finance-standin)",
              lambda ev: real(ev) and _out(ev).get("kind") == "order_placed", _order, "standins.py")

def register(mcp=None, lock=None):
    return {"standins": ON, "wait_sec": WAIT, "stall_sec": STALL}
