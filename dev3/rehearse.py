"""dev3 rehearsal: push a sample Pulse Studio chain to the shared hub so finance/legal/integrations have work.

  trend_spotted -> product_created -> listing_live (dev2's shape, price 49)
     -> order_placed WITH cost   (finance should emit margin_update)
     -> order_placed WITHOUT cost (finance should emit failed: missing pod_cost, never guessed)

Every event is contract-valid (departments/lib/events.validate): ts, dept, task_id, status, summary, mode at top level,
optional parent_id/actor/output/needs_approval, everything else inside output. mode is "mock" (rehearsal stand-ins).
actor is "rehearse-dev3" (not "dev3-*", so dev3/agent.py does NOT skip these as its own events).

Modes:
  --mode pulse (default): the real chain on main. POST /api/pulse/start {trend?} -> dev4 design/QA publish listing_live
      -> POST /api/ops/order {task_id, qty} -> ops order_placed. dev3/agent.py then reacts (legal, finance, integrations).
  --mode synthetic: posts the 5 contract events above directly (no dev4 chain needed).

Run:  python dev3/rehearse.py [--hub http://127.0.0.1:8810] [--mode pulse|synthetic] [--dry-run] [--trend "..."]
"""
import argparse, json, os, sys, time, urllib.request, uuid
from datetime import datetime, timezone

DEFAULT_HUB = (os.environ.get("HUB_URL") or os.environ.get("HUB") or "http://127.0.0.1:8810").rstrip("/")
ACTOR = "rehearse-dev3"


def ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def build_chain(run=None, trend="Sleepy office cats"):
    run = run or uuid.uuid4().hex[:6]
    t, p, l = f"reh-{run}-trend", f"reh-{run}-product", f"reh-{run}-listing"
    o1, o2 = f"reh-{run}-order1", f"reh-{run}-order2"

    def ev(dept, tid, summary, output, parent=None):
        e = {"ts": ts(), "dept": dept, "task_id": tid, "status": "done", "summary": summary, "mode": "mock",
             "actor": ACTOR, "output": output}
        if parent:
            e["parent_id"] = parent
        return e

    return [
        ev("research", t, f"Trend spotted: {trend}", {"kind": "trend_spotted", "trend": trend,
           "why": "rehearsal backup trend", "source": "x", "root_id": t}),
        ev("design", p, f"Product created: '{trend}' sticker", {"kind": "product_created", "title": f"{trend} sticker",
           "product": "sticker", "root_id": t}, t),
        ev("sales", l, "Listing live: Pulse Studio", {"kind": "listing_live", "product": "Pulse Studio", "url": "/pulse",
           "price": 49, "root_id": t}, p),
        ev("ops", o1, "Order placed: 2 x $49 (cost $14/unit)", {"kind": "order_placed", "qty": 2, "price_usd": 49,
           "unit_cost_usd": 14, "cost_usd": 28, "provider": "MOCK print-on-demand", "root_id": t}, l),
        ev("ops", o2, "Order placed: 1 x $49 (no cost on order)", {"kind": "order_placed", "qty": 1, "price_usd": 49,
           "provider": "MOCK print-on-demand", "root_id": t}, l),
    ]


def call(hub, path, body=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(hub.rstrip("/") + path, data=data, method=method or ("POST" if data else "GET"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read() or b"{}")


def post(hub, e):
    return call(hub, "/api/events", e)


def pulse(hub, trend=None, qty=2, wait=30.0, poll=1.0, sleep=time.sleep):
    """Real chain: /api/pulse/start, wait for listing_live on the design task, then /api/ops/order. Returns a report dict."""
    body = {"trend": trend, "source": "manual", "why": "dev3 rehearsal"} if trend else {}
    st = call(hub, "/api/pulse/start", body)
    root = st.get("trend_task")
    rep = {"trend_task": root, "listing_task": None, "order": None}
    if not root:
        rep["error"] = f"pulse/start returned {str(st)[:160]}"; return rep
    deadline = wait
    while deadline > 0 and not rep["listing_task"]:
        evs = call(hub, "/api/events?limit=500").get("events", [])
        prod = [e["task_id"] for e in evs if e.get("parent_id") == root and (e.get("output") or {}).get("kind") == "product_created"]
        live = [e for e in evs if e.get("task_id") in prod and (e.get("output") or {}).get("kind") == "listing_live"]
        if live:
            rep["listing_task"] = live[-1]["task_id"]; break
        if prod and any(e.get("task_id") in prod and e.get("status") in ("needs_approval", "failed", "rejected") and e.get("dept") == "qa" for e in evs):
            rep["error"] = f"product {prod[-1]} held by QA (founder/fail); approve it on /dashboard or pick another trend"; return rep
        sleep(poll); deadline -= poll
    if not rep["listing_task"]:
        rep["error"] = f"no listing_live within {wait:g}s"; return rep
    rep["order"] = call(hub, "/api/ops/order", {"task_id": rep["listing_task"], "qty": qty, "actor": ACTOR})
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--hub", default=DEFAULT_HUB)
    ap.add_argument("--trend", default="Sleepy office cats")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--mode", choices=("pulse", "synthetic"), default="pulse")
    ap.add_argument("--qty", type=int, default=2)
    ap.add_argument("--wait", type=float, default=30.0)
    a = ap.parse_args(argv)
    if a.mode == "pulse" and not a.dry_run:
        try:
            rep = pulse(a.hub, None if a.trend == "Sleepy office cats" else a.trend, a.qty, a.wait)
        except Exception as ex:
            print(f"FAIL pulse: {type(ex).__name__}: {ex}"); return 1
        print(json.dumps({k: v for k, v in rep.items() if k != "order"}))
        o = (rep.get("order") or {}).get("order") or {}
        if o:
            print(f"OK   order {o.get('order_id')} x{o.get('qty')} revenue ${o.get('revenue_usd')} cost ${o.get('cost_usd')} (MOCK POD, Stripe test)")
        return 0 if o else 1
    chain = build_chain(trend=a.trend)
    bad = 0
    for e in chain:
        if a.dry_run:
            print(json.dumps(e)); continue
        try:
            r = post(a.hub, e)
            print(f"OK   {e['dept']:<9} {e['output']['kind']:<16} {e['task_id']}" if r.get("ok") else f"FAIL {e['task_id']}: {r}")
            bad += 0 if r.get("ok") else 1
        except Exception as ex:
            body = getattr(ex, "read", lambda: b"")()
            print(f"FAIL {e['task_id']}: {type(ex).__name__} {body[:200]!r}"); bad += 1
    if not a.dry_run:
        print(f"posted {len(chain) - bad}/{len(chain)} to {a.hub}; root {chain[0]['task_id']}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
