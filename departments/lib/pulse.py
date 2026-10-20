"""Phase 2: Pulse Studio, a trend-to-product brand (dev4: Design 11, QA 13, Data/ops 12).
Chain (rules in the lib/auto.py engine, registered from lib/chains.py):
  trend_spotted (any dept except design/legal/integrations, e.g. research, grok-routine, POST /api/pulse/start actor 'pulse')
   -> Design: product_created {product_type, title, tagline, price_usd, cost_usd, image MOCK svg} + brand score / retry once
   -> QA product gate: fail on trademark / PII / offensive; founder on price outside $5-$60 or margin < 30%
   -> pass (or founder approve): listing page data/published/<task>/index.html + listing_live event (webhooks sales/engineering/marketing)
  POST /api/ops/order {task_id, qty} -> MOCK print-on-demand order (data/ops/orders.jsonl), Stripe TEST MODE only (no real charge,
   no Stripe call is made) -> order_placed (ops) + margin_update (computed_by ops; dev3 finance emits its own margin_update).
Everything generated here is MOCK (no XAI_API_KEY): SVG placeholder art, mock POD provider, mock payment id."""
import html, json, os, random, re, threading
from datetime import datetime, timezone
import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse
import events, auto, qa, design_loop

ROOT = os.environ.get("DEPT_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR, PUB, ORDERS = f"{ROOT}/data/design-out", f"{ROOT}/data/published", f"{ROOT}/data/ops/orders.jsonl"
BACKUP = f"{ROOT}/data/trends/backup.json"
BRAND = "Pulse Studio"; PALETTE = ["#7C3AED", "#22D3EE", "#0B0B1A", "#F472B6"]
PRICES = {"sticker": (6.0, 1.6), "tee": (28.0, 12.5), "poster": (22.0, 7.0)}   # (price_usd, POD cost_usd), MOCK catalogue
TRADEMARKS = ["nike", "adidas", "disney", "marvel", "apple", "pixar", "pokemon", "nintendo", "star wars", "coca-cola", "coke",
              "pepsi", "mcdonald", "starbucks", "tesla", "gucci", "louis vuitton", "supreme", "nfl", "nba", "fifa", "olympic",
              "barbie", "lego", "hello kitty", "harry potter", "taylor swift", "mickey"]
OFFENSIVE = ["kill", "hate", "nazi", "racist", "slur", "terror", "porn", "nsfw", "suicide", "shooting", "rape", "drugs"]
SKIP_DEPTS = {"design", "legal", "integrations", "qa"}
_olock = threading.Lock()

def _out(ev): return ev.get("output") or {}
def _now(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def _safe(s): return "".join(c for c in str(s) if c.isalnum() or c in "-_.")[:80] or "x"
def _find(task_id, kind):
    for e in reversed(events.read_all()):
        if e.get("task_id") == task_id and _out(e).get("kind") == kind: return e
    return None

def backup_trends():
    return json.load(open(BACKUP))["trends"]

# ---------- Design: product + MOCK svg + brand score/retry ----------
def _svg(path, title, tagline, ptype, palette):
    t, g = html.escape(title[:28]), html.escape(tagline[:44])
    shape = {"sticker": '<circle cx="256" cy="256" r="220"', "tee": '<path d="M136 96l64-32h112l64 32 56 72-56 40v240H136V208l-56-40z"',
             "poster": '<rect x="76" y="36" width="360" height="440" rx="12"'}[ptype]
    open(path, "w").write(f'''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
<rect width="512" height="512" fill="{palette[2] if len(palette) > 2 else '#111'}"/>{shape} fill="{palette[0]}" stroke="{palette[1]}" stroke-width="10"/>
<text x="256" y="236" font-family="sans-serif" font-size="30" font-weight="700" fill="#fff" text-anchor="middle">{t}</text>
<text x="256" y="276" font-family="sans-serif" font-size="16" fill="{palette[1]}" text-anchor="middle">{g}</text>
<text x="256" y="330" font-family="sans-serif" font-size="14" fill="#fff" text-anchor="middle">{BRAND} · {ptype}</text>
<text x="256" y="500" font-family="monospace" font-size="12" fill="#f88" text-anchor="middle">MOCK placeholder art (no XAI key)</text></svg>''')

def design_product(trend_ev):
    o = _out(trend_ev); trend = str(o.get("trend") or "").strip()[:80]
    ptype = o.get("product_type") if o.get("product_type") in PRICES else random.Random(trend).choice(list(PRICES))
    price, cost = PRICES[ptype]
    if o.get("price_usd") is not None: price = float(o["price_usd"])
    if o.get("cost_usd") is not None: cost = float(o["cost_usd"])
    tid = events.new_task_id("product"); parent = trend_ev["task_id"]; mode = "mock"
    title = trend.title(); tagline = f"{trend.lower()}: worn while it's trending" if ptype == "tee" else f"Catch the {trend.lower()} wave"
    os.makedirs(OUT_DIR, exist_ok=True)
    auto.emit("design", tid, "running", f"Design: making a {ptype} from trend '{trend}'", mode, {"kind": "product_brief", "trend": trend}, parent)
    def make(attempt, low):
        p = f"{OUT_DIR}/{_safe(tid)}-{ptype}-a{attempt}.MOCK.svg"
        _svg(p, title, tagline, ptype, design_loop.OFF_BRAND if low else PALETTE); return p
    path = make(1, bool(o.get("force_low_score")))
    s, reasons = design_loop.mock_score(path, BRAND, PALETTE); attempts, first = 1, None
    if s is not None and s < design_loop.THRESHOLD:
        auto.emit("design", tid, "running", f"Design: brand score {s} < {design_loop.THRESHOLD}, regenerating once", mode,
                  {"kind": "design_regenerate", "brand_score": s, "brand_reasons": reasons, "threshold": design_loop.THRESHOLD}, parent)
        first = s; path = make(2, False); s, reasons = design_loop.mock_score(path, BRAND, PALETTE); attempts = 2
    product = {"product_type": ptype, "title": title, "tagline": tagline, "price_usd": round(price, 2), "cost_usd": round(cost, 2),
               "image": path, "image_url": "/files/design-out-data/" + os.path.basename(path), "trend": trend,
               "trend_source": o.get("source"), "brand_score": s, "brand_reasons": reasons, "brand_scorer": design_loop.MOCK_SCORER,
               "attempts": attempts, "first_score": first, "mock": "MOCK: placeholder SVG + catalogue prices, no XAI key"}
    auto.emit("design", tid, "running", f"Design: product created, {ptype} '{title}' ${price:.2f} (brand {s})", mode,
              {"kind": "product_created", **product}, parent)
    return tid

# ---------- QA product gate ----------
def product_rules(p):
    text = " ".join(str(p.get(k) or "") for k in ("trend", "title", "tagline")).lower()
    hard, founder = [], []
    tm = [w for w in TRADEMARKS if re.search(r"\b" + re.escape(w) + r"\b", text)]
    if tm: hard.append("trademark: uses protected brand/IP name(s) " + ", ".join(tm))
    bad = [w for w in OFFENSIVE if re.search(r"\b" + re.escape(w), text)]
    if bad: hard.append("offensive: blocked keyword(s) " + ", ".join(bad))
    price, cost = float(p.get("price_usd") or 0), float(p.get("cost_usd") or 0)
    margin = round((price - cost) / price * 100, 1) if price > 0 else 0.0
    if not 5 <= price <= 60: founder.append(f"pricing: price ${price:.2f} outside $5-$60 needs founder")
    if margin < 30: founder.append(f"pricing: margin {margin}% < 30% needs founder")
    return hard, founder, margin

def qa_product(tid, parent):
    pe = _find(tid, "product_created"); p = _out(pe)
    hard, founder, margin = product_rules(p)
    base = qa.check({"dept": "design", "task_id": tid, "kind": "product_listing",
                     "content": f"{p.get('title')}. {p.get('tagline')}. Trend: {p.get('trend')}"}, log=False)
    hard += [r for r in base["reasons"] if r.startswith(("pii:", "policy: banned", "nonempty"))]
    verdict = "fail" if hard else ("founder" if founder else "pass")
    reasons = hard + founder or ["all product checks passed (trademark, PII, offensive, price $5-$60, margin >= 30%)"]
    status = {"pass": "approved", "fail": "rejected", "founder": "needs_approval"}[verdict]
    events.emit("qa", tid, status, f"QA {verdict} for design product_listing (margin {margin}%)", "mock",
                {"verdict": verdict, "for_dept": "design", "kind": "product_listing", "margin_pct": margin, "reasons": reasons[:6],
                 "checks": ["trademark", "offensive", "pii", "price_range", "margin"], "qa_mode": base.get("mode")},
                parent_id=parent, actor="dev4-qa-gate", needs_approval=(verdict == "founder"))
    if verdict == "pass": publish(tid, "auto")
    elif verdict == "fail":
        auto.emit("design", tid, "failed", f"Design: product blocked by QA ({reasons[0][:90]})", "mock",
                  {"kind": "product_blocked", "reasons": reasons[:4]}, parent)
    return verdict

# ---------- listing page + listing_live ----------
def publish(tid, executed_by):
    pe = _find(tid, "product_created"); p = _out(pe); parent = pe.get("parent_id")
    d = f"{PUB}/{_safe(tid)}"; os.makedirs(d, exist_ok=True)
    img = os.path.basename(p["image"]); open(f"{d}/{img}", "w").write(open(p["image"]).read())
    e = lambda k: html.escape(str(p.get(k, "")))
    page = f"""<!doctype html><html><head><meta charset=utf-8><title>{e('title')} | {BRAND}</title>
<style>body{{background:#0b0b1a;color:#eee;font-family:system-ui,sans-serif;display:flex;justify-content:center;padding:40px}}
.card{{background:#16162e;border:1px solid #7c3aed;border-radius:18px;padding:24px;max-width:420px;box-shadow:0 0 40px #7c3aed55}}
img{{width:100%;border-radius:12px}}.price{{font-size:32px;color:#22d3ee}}button{{background:#7c3aed;color:#fff;border:0;border-radius:10px;
padding:14px 20px;font-size:18px;cursor:pointer;width:100%}}.mock{{background:#7f1d1d;padding:6px 10px;border-radius:8px;font-size:12px}}</style></head>
<body><div class=card><div class=mock>MOCK listing · Stripe TEST MODE · mock print-on-demand · no real charge</div>
<h1>{e('title')}</h1><p>{e('tagline')}</p><img src="{img}" alt="{e('title')}"><p>{e('product_type')} · trend: {e('trend')} ({e('trend_source')})</p>
<div class=price>${p['price_usd']:.2f}</div><p><button id=buy>Buy (Stripe test mode)</button></p><pre id=r></pre></div>
<script>document.getElementById('buy').onclick=async()=>{{const r=await fetch('/api/ops/order',{{method:'POST',headers:{{'Content-Type':'application/json'}},
body:JSON.stringify({{task_id:{json.dumps(tid)},qty:1}})}});const j=await r.json();document.getElementById('r').textContent=j.ok?
'Order '+j.order.order_id+' placed (MOCK, test mode). Total $'+j.order.revenue_usd:JSON.stringify(j);}};</script></body></html>"""
    open(f"{d}/index.html", "w").write(page)
    json.dump({**p, "task_id": tid, "published_at": _now(), "executed_by": executed_by}, open(f"{d}/listing.json", "w"), indent=1)
    url = f"/files/published/{_safe(tid)}/index.html"
    ev = auto.emit("design", tid, "done", f"Listing live: {p['title']} {p['product_type']} ${p['price_usd']:.2f} ({executed_by})", "mock",
                   {"kind": "listing_live", "product": {k: p[k] for k in ("product_type", "title", "tagline", "price_usd", "cost_usd", "trend")},
                    "url": url, "image_url": f"/files/published/{_safe(tid)}/{img}", "listing_json": f"/files/published/{_safe(tid)}/listing.json",
                    "action": {"type": "listing_publish", "path": f"{d}/index.html", "url": url, "executed_by": executed_by}}, parent)
    _fan(ev, ("sales", "engineering", "marketing"))
    return url

def _fan(ev, depts):
    try: hooks = json.load(open(f"{ROOT}/data/webhooks.json"))
    except Exception: hooks = []
    urls = [h["url"] for h in hooks if h.get("dept") in depts]   # 'all' and design hooks already get it from server fan-out
    def send():
        for u in urls:
            try: r = httpx.post(u, json=ev, timeout=5); msg = f"OK {r.status_code}"
            except Exception as x: msg = f"FAIL {type(x).__name__}"
            with open(f"{ROOT}/logs/webhooks.log", "a") as f: f.write(f"{_now()} {msg} {u} task={ev['task_id']} listing_live\n")
    if urls: threading.Thread(target=send, daemon=True).start()

# ---------- Ops: MOCK print-on-demand order ----------
def totals():
    rows = []
    try: rows = [json.loads(l) for l in open(ORDERS) if l.strip()]
    except FileNotFoundError: pass
    rev = round(sum(r["revenue_usd"] for r in rows), 2); cost = round(sum(r["cost_usd"] for r in rows), 2)
    return {"orders_count": len(rows), "revenue_usd": rev, "cost_usd": cost, "profit_usd": round(rev - cost, 2),
            "margin_pct": round((rev - cost) / rev * 100, 1) if rev else None, "computed_by": "ops", "source": "data/ops/orders.jsonl (MOCK)"}

def order(task_id, qty=1, actor="api"):
    le = _find(task_id, "listing_live")
    if not le: raise LookupError(f"no live listing for task {task_id}")
    qty = int(qty)
    if not 1 <= qty <= 20: raise ValueError("qty must be 1..20")
    p = _out(le)["product"]; oid = events.new_task_id("order")
    rec = {"order_id": oid, "listing_task": task_id, "qty": qty, "title": p["title"], "product_type": p["product_type"],
           "unit_price_usd": p["price_usd"], "unit_cost_usd": p["cost_usd"], "revenue_usd": round(p["price_usd"] * qty, 2),
           "cost_usd": round(p["cost_usd"] * qty, 2), "provider": "MOCK print-on-demand (no real order placed)",
           "payment": {"provider": "stripe", "mode": "test", "id": "MOCK-pi_" + oid.split("-")[1], "note": "MOCK, no Stripe call, no charge"},
           "ts": _now(), "actor": actor, "mock": True}
    with _olock:
        os.makedirs(os.path.dirname(ORDERS), exist_ok=True)
        with open(ORDERS, "a") as f: f.write(json.dumps(rec) + "\n")
        t = totals()
    events.emit("ops", oid, "done", f"Ops: MOCK POD order {oid} x{qty} {p['title']} ${rec['revenue_usd']:.2f} (Stripe test mode)", "mock",
                {"kind": "order_placed", **{k: rec[k] for k in ("order_id", "listing_task", "qty", "revenue_usd", "cost_usd", "provider", "payment")},
                 "action": {"type": "pod_order", "path": ORDERS, "executed_by": "auto" if actor == "auto" else "ops"}}, task_id, "dev4-ops")
    events.emit("ops", oid, "done", f"Ops margin (computed by ops): {t['orders_count']} orders, ${t['revenue_usd']:.2f} revenue, {t['margin_pct']}% margin",
                "mock", {"kind": "margin_update", "computed_by": "ops", "order_id": oid, "revenue_usd": rec["revenue_usd"],
                         "cost_usd": rec["cost_usd"], "margin_pct": round((rec["revenue_usd"] - rec["cost_usd"]) / rec["revenue_usd"] * 100, 1),
                         "totals": t}, task_id, "dev4-ops")
    return {"ok": True, "order": rec, "totals": t}

def start(body, actor="pulse"):
    b = body or {}; trend = str(b.get("trend") or "").strip()
    if trend:
        src = b.get("source") if b.get("source") in ("x", "backup", "manual") else "manual"
        t = {"trend": trend[:80], "why": str(b.get("why") or "given by caller")[:200]}
    else:
        bt = backup_trends(); t = dict(bt[int(b.get("backup_index", 0)) % len(bt)]); src = "backup"
    out = {"kind": "trend_spotted", "trend": t["trend"], "why": t.get("why"), "source": src}
    for k in ("product_type", "price_usd", "cost_usd", "force_low_score"):
        if k in b: out[k] = b[k]
        elif k in t: out[k] = t[k]
    ev = events.emit("research", events.new_task_id("pulse"), "done", f"Trend spotted ({src}): {t['trend']}", "mock" if src != "x" else "live",
                     out, None, actor)
    return {"ok": True, "trend_task": ev["task_id"], "trend": out, "follow": f"/api/events?limit=50"}

# ---------- rules ----------
def _on_trend(ev):
    tid = design_product(ev); qa_product(tid, ev["task_id"])
auto.rule("pulse.trend->product", "trend_spotted event (research / grok-routine / pulse; not design/legal/integrations)",
          "Design makes product (brand score, retry once) -> QA product gate -> pass: listing page + listing_live; founder: queue; fail: blocked",
          lambda ev: _out(ev).get("kind") == "trend_spotted" and ev.get("dept") not in SKIP_DEPTS and ev.get("status") != "failed", _on_trend, "pulse.py")
auto.rule("pulse.founder_approve->listing", "founder approved a design product task (price/margin gate)", "publish listing page + listing_live",
          lambda ev: ev.get("actor") == "founder" and ev["status"] == "approved" and ev["dept"] == "design" and _find(ev["task_id"], "product_created") is not None
          and _find(ev["task_id"], "listing_live") is None, lambda ev: publish(ev["task_id"], "founder"), "pulse.py")

def register(mcp, lock=None):
    import asyncio
    async def _b(req):
        try: return await req.json() or {}
        except Exception: return {}
    @mcp.custom_route("/api/pulse/start", methods=["POST"])
    async def api_start(req: Request): return JSONResponse(await asyncio.to_thread(start, await _b(req)))
    @mcp.custom_route("/api/pulse/trends", methods=["GET"])
    async def api_trends(req: Request): return JSONResponse({"backup": backup_trends()})
    @mcp.custom_route("/api/pulse/listings", methods=["GET"])
    async def api_listings(req: Request):   # for /store: live listings, newest first
        ls = [{"task_id": e["task_id"], "ts": e["ts"], **_out(e).get("product", {}), "url": _out(e).get("url"), "image_url": _out(e).get("image_url"),
               "executed_by": (_out(e).get("action") or {}).get("executed_by"), "mode": e["mode"]}
              for e in events.read_all() if e.get("dept") == "design" and _out(e).get("kind") == "listing_live"]
        return JSONResponse({"listings": ls[::-1], "totals": totals(), "note": "MOCK listings, Stripe test mode"})
    @mcp.custom_route("/api/ops/order", methods=["POST"])
    async def api_order(req: Request):
        b = await _b(req)
        try: return JSONResponse(await asyncio.to_thread(order, b.get("task_id", ""), b.get("qty", 1), str(b.get("actor", "api"))[:60]))
        except LookupError as e: return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
        except ValueError as e: return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    @mcp.tool(name="pulse.start")
    async def pulse_start(trend: str = "", why: str = "", source: str = "manual") -> dict:
        """Pulse Studio: start trend -> product -> QA -> listing chain. Empty trend uses a safe backup trend. source: x|backup|manual."""
        return await asyncio.to_thread(start, {"trend": trend, "why": why, "source": source}, "pulse")
    @mcp.tool(name="ops.order")
    async def ops_order(task_id: str, qty: int = 1) -> dict:
        """Place a MOCK print-on-demand order for a live listing (Stripe test mode, no charge)."""
        return await asyncio.to_thread(order, task_id, qty, "mcp")
    return ["/api/pulse/start", "/api/pulse/trends", "/api/pulse/listings", "/api/ops/order", "pulse.start", "ops.order"]
