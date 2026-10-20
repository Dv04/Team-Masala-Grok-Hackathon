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

HUB = os.environ.get("HUB", "http://127.0.0.1:8810").rstrip("/")
POLL_SEC = float(os.environ.get("DEV3_POLL_SEC", "3"))
STALL_SEC = float(os.environ.get("DEV3_STALL_SEC", "120"))
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
    cost = pick("cost_usd", "pod_cost", "unit_cost", "cost")
    if price is None or cost is None:
        missing = [n for n, v in (("price", price), ("pod_cost", cost)) if v is None]
        return {"kind": "margin_update", "ok": False, "missing": missing, "order_task": order["task_id"],
                "reason": f"order_placed is missing {missing}; margin not computed (never guessed)"}
    revenue = round(price * qty, 2)
    fees = round(revenue * FEE_PCT + FEE_FIXED, 2)
    cogs = round(cost * qty, 2)
    margin = round(revenue - cogs - fees, 2)
    pct = round(margin / revenue, 4) if revenue else 0.0
    return {"kind": "margin_update", "ok": True, "order_task": order["task_id"], "qty": qty, "revenue": revenue,
            "cogs": cogs, "payment_fees": fees, "fee_model": "stripe 2.9% + $0.30 (test mode)",
            "margin": margin, "margin_pct": pct, "floor_pct": MARGIN_FLOOR, "under_floor": pct < MARGIN_FLOOR}


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
    return {"kind": "legal_review", "verdict": "flag" if issues else "pass", "issues": issues,
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

    for e in events:
        k = kind(e)
        if k in CHAIN and e.get("dept") != "integrations":
            r = roots.setdefault(root(e), {})
            r.setdefault(k, parse_ts(e.get("ts", "")))
    out = {}
    for r, hops in roots.items():
        if "trend_spotted" not in hops:
            continue
        done = [h for h in CHAIN if h in hops]
        nxt = next((h for h in CHAIN if h not in hops), None)
        out[r] = {"hops": done, "next": nxt, "last_ts": max(hops.values())}
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

    def _emit(self, dept, task_id, status, summary, output, parent_id=None, needs_approval=None):
        ev = {"ts": now(), "dept": dept, "task_id": task_id, "status": status, "summary": summary[:200],
              "actor": f"dev3-{dept}", "mode": "live", "output": output}
        if parent_id:
            ev["parent_id"] = parent_id
        if needs_approval is not None:
            ev["needs_approval"] = needs_approval
        return http("POST", "/api/events", ev)

    def qa(self, task_id, review):
        """Route a legal flag through dev4's QA gate (kind 'legal' always goes to the founder queue)."""
        try:
            return http("POST", "/api/qa/check", {"dept": "legal", "task_id": task_id, "kind": "legal",
                                                  "content": "; ".join(review["issues"]), "mode": "live"})
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
                if not out["ok"]:
                    self.emit("finance", tid, "failed", out["reason"], out, parent_id=e["task_id"])
                elif out["under_floor"]:
                    self.emit("finance", tid, "needs_approval",
                              f"Margin {out['margin_pct']:.0%} (${out['margin']}) under {MARGIN_FLOOR:.0%} floor; founder to approve price",
                              out, parent_id=e["task_id"], needs_approval=True)
                else:
                    self.emit("finance", tid, "done",
                              f"Margin ${out['margin']} ({out['margin_pct']:.0%}) on ${out['revenue']} order",
                              out, parent_id=e["task_id"])
                n += 1
            if k in ("trend_spotted", "product_created") and self.once_key(f"legal:{e['task_id']}"):
                out = legal_review(e)
                tid = f"legal-{e['task_id']}"
                if out["verdict"] == "flag":
                    self.emit("legal", tid, "needs_approval", "Legal flag: " + "; ".join(out["issues"])[:180],
                              out, parent_id=e["task_id"], needs_approval=True)
                    self.qa(tid, out)
                else:
                    self.emit("legal", tid, "done", f"Legal pre-check pass on {k} {e['task_id']}", out,
                              parent_id=e["task_id"])
                n += 1
        for r, st in chain_state(events).items():
            if st["next"] and t - st["last_ts"] > STALL_SEC and self.once_key(f"stall:{r}:{st['next']}"):
                self.emit("integrations", f"int-stall-{r}-{st['next']}", "done",
                          f"Chain {r} stalled: no {st['next']} for {int(t - st['last_ts'])}s (has {', '.join(st['hops'])})",
                          {"kind": "chain_stalled", "root": r, "hops": st["hops"], "missing": st["next"],
                           "stall_sec": STALL_SEC}, parent_id=r)
                n += 1
            if st["next"] is None and self.once_key(f"chaindone:{r}"):
                self.emit("integrations", f"int-chain-{r}", "done", f"Chain {r} complete: trend -> margin",
                          {"kind": "chain_complete", "root": r, "hops": st["hops"]}, parent_id=r)
                n += 1
        if n:
            self._save()
        return n


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
