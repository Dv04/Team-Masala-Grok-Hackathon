"""dev3 departments: finance, legal, integrations.

Plugs into the shared departments/ hub (dev4) through the same contract everyone uses:
reads GET /api/events, writes POST /api/events. Stdlib only, no keys, no LLM calls.

  finance       order_placed                   -> margin_update (founder queue if margin is under the floor)
  legal         trend_spotted / product_created -> legal_review pass | flag (flag -> founder queue)
  integrations  watches every dept + the Pulse Studio chain, emits chain_stalled when a hop is missing

Run:  python dev3/agent.py            (HUB=http://127.0.0.1:8810 by default)
      python dev3/agent.py --once     (one pass, for tests/demo)
"""
import argparse, json, os, re, sys, time, urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:  # optional helpers (stdlib only): live Grok via xAI Responses API + qa.check bridge. Agent works without them.
    import grok
except Exception:
    grok = None
try:
    import qa_bridge
except Exception:
    qa_bridge = None

HUB = os.environ.get("HUB", "http://127.0.0.1:8810").rstrip("/")
POLL_SEC = float(os.environ.get("DEV3_POLL_SEC", "3"))
STALL_SEC = float(os.environ.get("DEV3_STALL_SEC", "120"))
# order_placed waits on a buyer, not a bot, so that hop gets its own (longer) stall window.
STALL_ORDER_SEC = float(os.environ.get("DEV3_STALL_ORDER_SEC", "300"))
GROK_ON_PASS = os.environ.get("DEV3_GROK_ON_PASS", "1") != "0"   # Grok second opinion on legal passes too (flags always)
MARGIN_FLOOR = float(os.environ.get("DEV3_MARGIN_FLOOR", "0.25"))
# Stripe standard US card pricing (2.9% + $0.30); Pulse Studio runs Stripe in test mode.
FEE_PCT, FEE_FIXED = 0.029, 0.30
SEEN_FILE = os.environ.get("DEV3_SEEN", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".seen.json"))
MY_DEPTS = ("finance", "legal", "integrations")
ALL_DEPTS = ("orchestrator", "research", "marketing", "sales", "support", "engineering",
             "finance", "legal", "integrations", "hr", "design", "ops", "qa")
CHAIN = ("trend_spotted", "product_created", "listing_live", "order_placed", "margin_update")

# Marks that a trend-to-merch shop must not print without a license. Not a trademark database; a rules pre-check.
MARKS = ["nike", "adidas", "disney", "marvel", "pixar", "star wars", "pokemon", "pokémon", "nintendo", "mario",
         "hello kitty", "barbie", "lego", "coca-cola", "pepsi", "apple", "iphone", "tesla", "nfl", "nba", "mlb",
         "fifa", "olympic", "super bowl", "harry potter", "taylor swift", "beyonce", "spotify", "netflix",
         "minecraft", "fortnite", "x.com", "twitter", "grok", "openai", "chatgpt", "louis vuitton", "gucci",
         "supreme", "ferrari", "lamborghini", "mcdonald", "starbucks", "red bull", "sanrio", "simpsons"]
MARK_RE = re.compile(r"(?<![a-z])(" + "|".join(re.escape(m) for m in MARKS) + r")(?![a-z])", re.I)
SYMBOL_RE = re.compile(r"[™®©]")
PERSON_RE = re.compile(r"\b(elon musk|trump|biden|kamala|obama|drake|kanye|mrbeast|kardashian)\b", re.I)
TOS_RE = re.compile(r"\b(nsfw|nude|gore|hate|nazi|terror\w*|shooting|massacre|counterfeit|replica|fake id)\b", re.I)


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()  # hub writes millis: ...12.738Z
    except Exception:
        return time.time()


def http(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(HUB + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read() or b"{}")


def kind(ev):
    return (ev.get("output") or {}).get("kind")


def num(o, *keys, default=None):
    for k in keys:
        try:
            if o.get(k) is not None:
                return float(o[k])
        except (TypeError, ValueError):
            pass
    return default


# ---------------- finance ----------------
def _price_sources(order, by_id=None):
    """output, output.product, output.order, then the parent chain's output.product (listing_live carries
    product {price_usd, cost_usd})."""
    o = order.get("output") or {}
    srcs = [o, o.get("product") or {}, o.get("order") or {}]
    e, hops = order, 0
    while by_id and e.get("parent_id") in by_id and hops < 6:
        e = by_id[e["parent_id"]]; hops += 1
        po = e.get("output") or {}
        srcs += [po.get("product") or {}, po]
    return [x for x in srcs if isinstance(x, dict)]


def finance_margin(order, by_id=None):
    """order event -> margin_update output. Missing price or cost is reported, never guessed."""
    srcs = _price_sources(order, by_id)
    pick = lambda *keys: next((v for v in (num(x, *keys) for x in srcs) if v is not None), None)
    qty = pick("qty", "quantity") or 1.0
    price = pick("price_usd", "price", "unit_price")
    # Per-unit cost first (order unit_cost_usd, then product/listing cost_usd). The order's own top-level cost_usd is the
    # ORDER TOTAL on the hub (qty x unit), so it is used as-is and never multiplied by qty again.
    cost = pick("unit_cost_usd", "unit_cost", "pod_cost")
    if cost is None:
        cost = next((v for v in (num(x, "cost_usd", "cost") for x in srcs[1:]) if v is not None), None)
    total_cost = num(srcs[0], "cost_usd", "cost") if cost is None else None
    if price is None or (cost is None and total_cost is None):
        missing = [n for n, v in (("price", price), ("pod_cost", cost if cost is not None else total_cost)) if v is None]
        return {"kind": "margin_update", "ok": False, "missing": missing, "order_task": order["task_id"],
                "reason": f"order_placed is missing {missing}; margin not computed (never guessed)"}
    revenue = round(price * qty, 2)
    fees = round(revenue * FEE_PCT + FEE_FIXED, 2)
    cogs = round(cost * qty, 2) if cost is not None else round(total_cost, 2)
    margin = round(revenue - cogs - fees, 2)
    pct = round(margin / revenue, 4) if revenue else 0.0
    return {"kind": "margin_update", "ok": True, "order_task": order["task_id"], "qty": qty, "revenue": revenue,
            "cogs": cogs, "payment_fees": fees, "fee_model": "stripe 2.9% + $0.30 (test mode)",
            "margin": margin, "margin_pct": round(pct * 100, 1), "margin_frac": pct,   # margin_pct in percent, like ops
            "floor_pct": round(MARGIN_FLOOR * 100, 1), "under_floor": pct < MARGIN_FLOOR}


# ---------------- legal ----------------
def legal_review(ev):
    o = ev.get("output") or {}
    text = " ".join(str(x) for x in (ev.get("summary"), o.get("trend"), o.get("title"), o.get("name"),
                                     o.get("product"), o.get("slogan"), o.get("caption"), o.get("text")) if x)
    issues = []
    for m in sorted({m.group(1).lower() for m in MARK_RE.finditer(text)}):
        issues.append(f"trademark: '{m}' is a protected mark; needs license or rewording")
    if SYMBOL_RE.search(text):
        issues.append("trademark: text contains a TM/R/C symbol")
    for m in sorted({m.group(1).lower() for m in PERSON_RE.finditer(text)}):
        issues.append(f"right of publicity: real person '{m}' on merch needs consent")
    for m in sorted({m.group(1).lower() for m in TOS_RE.finditer(text)}):
        issues.append(f"platform ToS: '{m}' is restricted content for POD/Stripe")
    # kind legal_precheck = the PR #2 contract / dev4 stand-in kind (reasons = issues, same as the stand-in)
    return {"kind": "legal_precheck", "review": "legal_review", "verdict": "flag" if issues else "pass", "issues": issues,
            "reasons": issues,
            "checked": ev["task_id"], "checked_kind": kind(ev),
            "engine": "rules pre-check (mark list + ToS words), not a trademark database search"}


# ---------------- integrations ----------------
def chain_state(events):
    """Group Pulse Studio chain events by root (parent_id chain or output.root_id) and find the next missing hop."""
    by_id, roots = {}, {}
    for e in events:
        by_id.setdefault(e["task_id"], e)

    def root(e, depth=0):
        o = e.get("output") or {}
        if o.get("root_id"):
            return o["root_id"]
        p = e.get("parent_id")
        if p and p in by_id and depth < 8:
            return root(by_id[p], depth + 1)
        return p or e["task_id"]

    latest, waiting, trend_ids = {}, set(), {}
    for e in events:
        latest[e["task_id"]] = e
    for e in latest.values():   # founder-gated or blocked chains are waiting on a human, not stalled
        if e.get("dept") != "integrations" and (e.get("status") == "needs_approval" or kind(e) == "product_blocked"):
            waiting.add(root(e))
    for e in events:
        k = kind(e)
        if k in CHAIN and e.get("dept") != "integrations":
            r = roots.setdefault(root(e), {})
            r.setdefault(k, parse_ts(e.get("ts", "")))
            if k == "trend_spotted":
                trend_ids.setdefault(root(e), e["task_id"])
    out = {}
    for r, hops in roots.items():
        if "trend_spotted" not in hops:
            continue
        done = [h for h in CHAIN if h in hops]
        nxt = next((h for h in CHAIN if h not in hops), None)
        out[r] = {"hops": done, "next": nxt, "last_ts": max(hops.values()), "waiting": r in waiting,
                  "trend_task": trend_ids.get(r)}
    return out


def connection_map(events, t=None):
    t = time.time() if t is None else t
    last = {}
    for e in events:
        last[e.get("dept")] = e
    m = {}
    for d in ALL_DEPTS:
        e = last.get(d)
        m[d] = ({"connected": True, "last_status": e["status"], "last_kind": kind(e),
                 "age_sec": int(t - parse_ts(e.get("ts", "")))} if e else {"connected": False})
    return m


# ---------------- routed tasks (orchestrator /request -> POST /api/tasks -> queued event output.kind "task") ----------------
def open_tasks(events):
    """Queued task events for finance/legal/integrations that nobody has moved past queued yet (hub task contract:
    actions.create_task emits {dept, task_id, status:queued, parent_id, output:{kind:task, title, detail}})."""
    latest = {}
    for e in events:
        latest[e.get("task_id")] = e.get("status")
    return [e for e in events if task_dept(e) and e.get("status") == "queued" and kind(e) == "task"
            and latest.get(e.get("task_id")) == "queued"]


def task_dept(ev):
    """finance/legal/integrations if this task event is addressed to us (event dept or output.for_dept), else None."""
    d = (ev.get("output") or {}).get("for_dept") or ev.get("dept")
    d = str(d or "").lower()
    return d if d in MY_DEPTS else None


def task_text(ev):
    o = ev.get("output") or {}
    d = o.get("detail")
    detail = d.get("text") if isinstance(d, dict) else d
    return str(o.get("title") or ev.get("summary") or ""), str(detail or "")


def finance_report(events):
    """All orders on the log -> totals (same margin model as margin_update)."""
    by_id = {x["task_id"]: x for x in events}   # same lookup as the order_placed path (latest event per task, e.g. listing_live)
    rows = [finance_margin(e, by_id) for e in events if kind(e) == "order_placed"]
    ok = [r for r in rows if r["ok"]]
    rev = round(sum(r["revenue"] for r in ok), 2); cogs = round(sum(r["cogs"] for r in ok), 2)
    fees = round(sum(r["payment_fees"] for r in ok), 2); margin = round(rev - cogs - fees, 2)
    return {"kind": "finance_report", "ok": True, "orders": len(rows), "orders_priced": len(ok), "revenue": rev,
            "cogs": cogs, "payment_fees": fees, "margin": margin, "margin_pct": round(margin / rev * 100, 1) if rev else 0.0,
            "margin_frac": round(margin / rev, 4) if rev else 0.0,
            "floor_pct": round(MARGIN_FLOOR * 100, 1), "under_floor": bool(rev) and margin / rev < MARGIN_FLOOR,
            "fee_model": "stripe 2.9% + $0.30 (test mode)"}


# ---------------- loop ----------------
class Agent:
    def __init__(self, emit=None):
        self.seen = self._load()
        self.emit = emit or self._emit

    def _load(self):
        try:
            with open(SEEN_FILE) as f:
                return set(json.load(f))
        except Exception:
            return set()

    def _save(self):
        try:
            with open(SEEN_FILE, "w") as f:
                json.dump(sorted(self.seen), f)
        except OSError:
            pass

    def _emit(self, dept, task_id, status, summary, output, parent_id=None, needs_approval=None, mode="mock"):
        ev = {"ts": now(), "dept": dept, "task_id": task_id, "status": status, "summary": summary[:200],
              "actor": f"dev3-{dept}", "mode": mode, "output": output}
        if parent_id:
            ev["parent_id"] = parent_id
        if needs_approval is not None:
            ev["needs_approval"] = needs_approval
        return http("POST", "/api/events", ev)

    def qa(self, task_id, review, mode="mock"):
        """Route a legal flag through dev4's QA gate (kind 'legal' always goes to the founder queue)."""
        if qa_bridge:
            r = qa_bridge.legal_check(task_id, review, hub=HUB, mode=mode, opinion=review.get("grok"))
            if r and r.get("verdict") == "unavailable":
                print(f"{now()} qa.check unavailable for {task_id}: {r.get('error')}", file=sys.stderr, flush=True)
            return r
        try:
            return http("POST", "/api/qa/check", {"dept": "legal", "task_id": task_id, "kind": "legal",
                                                  "content": "; ".join(review["issues"]), "mode": mode})
        except Exception as e:
            print(f"{now()} qa.check failed for {task_id}: {e}", file=sys.stderr, flush=True)

    def once_key(self, key):
        if key in self.seen:
            return False
        self.seen.add(key)
        return True

    def announce(self):
        if not self.once_key("announce"):
            return
        roles = {"finance": "margin tracking on order_placed", "legal": "trademark/IP + ToS pre-check on trends/products",
                 "integrations": "connection map + chain watcher for all 13 depts"}
        for d in MY_DEPTS:
            self.emit(d, f"dev3-{d}-online", "done", f"{d} connected to shared hub ({roles[d]})",
                      {"kind": "dept_online", "owner": "dev3", "role": roles[d]})

    def step(self, events, t=None):
        t = time.time() if t is None else t
        n = 0
        for e in events:
            if str(e.get("actor", "")).startswith("dev3-"):
                continue
            k = kind(e)
            if k == "order_placed" and self.once_key(f"fin:{e['task_id']}"):
                out = finance_margin(e, {x["task_id"]: x for x in events})
                tid = f"fin-{e['task_id']}"
                mode = "mock"
                if out["ok"] and grok:
                    out["grok"] = grok.margin_summary(out)
                    mode = "live" if out["grok"].get("mode") == "live" else "mock"
                if not out["ok"]:
                    self.emit("finance", tid, "failed", out["reason"], out, parent_id=e["task_id"], mode=mode)
                elif out["under_floor"]:
                    self.emit("finance", tid, "needs_approval",
                              f"Margin {out['margin_frac']:.0%} (${out['margin']}) under {MARGIN_FLOOR:.0%} floor; founder to approve price",
                              out, parent_id=e["task_id"], needs_approval=True, mode=mode)
                    if qa_bridge:
                        qa_bridge.margin_check(tid, out, hub=HUB, mode=mode)
                else:
                    self.emit("finance", tid, "done",
                              f"Margin ${out['margin']} ({out['margin_frac']:.0%}) on ${out['revenue']} order",
                              out, parent_id=e["task_id"], mode=mode)
                n += 1
            if k in ("trend_spotted", "product_created") and self.once_key(f"legal:{e['task_id']}"):
                out = legal_review(e)
                tid = f"legal-{e['task_id']}"
                mode = "mock"
                if grok and (out["verdict"] == "flag" or GROK_ON_PASS):
                    op = grok.legal_opinion(dict(e, output=dict(e.get("output") or {}, issues=out["issues"])))
                    out["grok"] = op
                    mode = "live" if op.get("mode") == "live" else "mock"
                    if op.get("mode") == "live" and op.get("verdict") == "flag" and out["verdict"] == "pass":
                        out["verdict"] = "flag"   # Grok caught something the rule list missed: still founder-gated, never auto-blocked
                        out["issues"].append("grok: " + str(op.get("opinion", ""))[:160])
                        out["engine"] += " + Grok second opinion"
                if out["verdict"] == "flag":
                    self.emit("legal", tid, "needs_approval", "Legal flag: " + "; ".join(out["issues"])[:180],
                              out, parent_id=e["task_id"], needs_approval=True, mode=mode)
                    self.qa(tid, out, mode=mode)
                else:
                    self.emit("legal", tid, "done", f"Legal pre-check pass on {k} {e['task_id']}"
                              + (" (Grok agrees)" if mode == "live" else ""), out, parent_id=e["task_id"], mode=mode)
                n += 1
        for e in open_tasks(events):
            if self.once_key(f"task:{e['task_id']}"):
                self.handle_task(e, events, t)
                n += 1
        for r, st in chain_state(events).items():
            window = STALL_ORDER_SEC if st["next"] == "order_placed" else STALL_SEC
            if st["next"] and self.once_key(f"watch:{r}"):
                # tell dev4's integrations stand-in the real dept is watching this chain (else it fires chain_stalled at 30s)
                self.emit("integrations", f"int-watch-{r}", "running", f"Watching chain {r}: trend_spotted seen",
                          {"kind": "chain_watch", "root": r, "trend_task": st["trend_task"], "hops": st["hops"], "next": st["next"]}, parent_id=r)
                n += 1
            if st["next"] and not st["waiting"] and t - st["last_ts"] > window and self.once_key(f"stall:{r}:{st['next']}"):
                self.emit("integrations", f"int-stall-{r}-{st['next']}", "done",
                          f"Chain {r} stalled: no {st['next']} for {int(t - st['last_ts'])}s (has {', '.join(st['hops'])})",
                          {"kind": "chain_stalled", "root": r, "hops": st["hops"], "missing": st["next"],
                           "stall_sec": window}, parent_id=r)
                n += 1
            if st["next"] is None and self.once_key(f"chaindone:{r}"):
                self.emit("integrations", f"int-chain-{r}", "done", f"Chain {r} complete: trend -> margin",
                          {"kind": "chain_complete", "root": r, "hops": st["hops"]}, parent_id=r)
                n += 1
        if n:
            self._save()
        return n


def _handle_task(self, e, events, t=None):
    """Claim a routed task (running), do the dept's work, then post the reply as a NEW task (parent_id = incoming task id)
    and close the incoming task with the same status, so the hub/dashboard can link reply -> task -> request."""
    dept, tid, parent = task_dept(e), e["task_id"], e.get("parent_id")
    rid = f"{ {'finance': 'fin', 'legal': 'legal', 'integrations': 'int'}.get(dept, dept)}-{tid}"
    raw_emit = self.emit

    def reply(d, _tid, status, summ, out=None, parent_id=None, **kw):
        raw_emit(d, rid, status, summ, out, parent_id=tid, **kw)
        raw_emit(d, tid, status, summ, {"kind": "task_closed", "reply_task_id": rid}, parent_id=parent,
                 **{k: v for k, v in kw.items() if k == "mode"})
    title, detail = task_text(e)
    self.emit(dept, tid, "running", f"{dept} picked up task: {title}"[:200],
              {"kind": "task_claimed", "title": title, "owner": "dev3"}, parent_id=parent)
    try:
        mode = "mock"
        if dept == "finance":
            out = finance_report(events)
            if grok and out["orders_priced"]:
                out["grok"] = grok.margin_summary(out)
                mode = "live" if out["grok"].get("mode") == "live" else "mock"
            out.update({"task": title, "request": detail[:300]})
            summ = (f"Finance: {out['orders_priced']} priced orders, ${out['revenue']} revenue, margin ${out['margin']} "
                    f"({out['margin_frac']:.0%})" if out["orders_priced"] else "Finance: no priced orders on the log yet")
            status = "needs_approval" if out["under_floor"] else "done"
            reply(dept, tid, status, summ, out, parent_id=parent, needs_approval=status == "needs_approval", mode=mode)
            if status == "needs_approval" and qa_bridge:
                qa_bridge.margin_check(rid, out, hub=HUB, mode=mode)
        elif dept == "legal":
            ev = {"task_id": tid, "summary": title, "output": {"kind": "task", "title": title, "text": detail}}
            out = legal_review(ev)
            if grok:
                op = grok.legal_opinion(dict(ev, output=dict(ev["output"], issues=out["issues"])))
                out["grok"] = op
                mode = "live" if op.get("mode") == "live" else "mock"
                if mode == "live" and op.get("verdict") == "flag" and out["verdict"] == "pass":
                    out["verdict"] = "flag"; out["issues"].append("grok: " + str(op.get("opinion", ""))[:160])
            out["task"] = title
            if out["verdict"] == "flag":
                reply(dept, tid, "needs_approval", "Legal review flag: " + "; ".join(out["issues"])[:170], out,
                          parent_id=parent, needs_approval=True, mode=mode)
                self.qa(rid, out, mode=mode)
            else:
                reply(dept, tid, "done", f"Legal review pass: {title}"[:200], out, parent_id=parent, mode=mode)
        else:  # integrations
            cm = connection_map(events, t)
            chains = chain_state(events)
            off = [d for d, v in cm.items() if not v["connected"]]
            out = {"kind": "integration_status", "task": title, "depts": cm, "connected": 13 - len(off), "waiting_on": off,
                   "chains": {r: {"hops": c["hops"], "next": c["next"]} for r, c in list(chains.items())[-10:]}}
            reply(dept, tid, "done", f"Integrations: {13 - len(off)}/13 depts connected, {len(chains)} Pulse chains tracked",
                      out, parent_id=parent)
    except Exception as ex:
        reply(dept, tid, "failed", f"{dept} task failed: {type(ex).__name__}"[:200],
                  {"kind": "task_failed", "error": f"{type(ex).__name__}: {ex}"[:300]}, parent_id=parent)


Agent.handle_task = _handle_task


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    agent = Agent()
    while True:
        try:
            agent.announce()
            evs = http("GET", "/api/events?limit=1000").get("events", [])
            n = agent.step(evs)
            if n:
                print(f"{now()} emitted {n}", flush=True)
            if agent.once_key(f"map:{int(time.time()) // 300}"):
                cm = connection_map(evs)
                off = [d for d, v in cm.items() if not v["connected"]]
                agent.emit("integrations", f"int-map-{int(time.time()) // 300}", "done",
                           f"Connection map: {13 - len(off)}/13 depts connected" + (f"; waiting on {', '.join(off)}" if off else ""),
                           {"kind": "connection_map", "depts": cm})
        except Exception as e:
            print(f"{now()} hub error: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        if a.once:
            return
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
