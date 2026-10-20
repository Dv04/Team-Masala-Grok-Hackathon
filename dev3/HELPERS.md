# dev3 helpers (opt-in, built by dev3's Grok Bot)

New files only; `dev3/agent.py` and `departments/` are untouched. Stdlib Python, no new deps.

| File | What it does |
|---|---|
| `grok.py` | `legal_opinion(review_or_event)` and `margin_summary(margin_output)` call the xAI Responses API (`POST https://api.x.ai/v1/responses`, model `XAI_MODEL`, default `grok-4.3`, reasoning effort low, 20 s timeout) **only when `XAI_API_KEY` is set**. Otherwise, or on any error, they return a deterministic fallback labeled `mode: "mock"`. They never raise and never log the key. |
| `qa_bridge.py` | `margin_check(task_id, margin_output)` sends margins under the floor to `POST /api/qa/check` with kind `pricing`. `legal_check(task_id, legal_review, opinion=None)` sends legal results with kind `legal`. The body is exactly `{dept, task_id, kind, content, context?, mode?}`. Hub down returns `{"verdict": "unavailable", ...}`. |
| `rehearse.py` | `--mode pulse` (default) runs the real chain on main: `POST /api/pulse/start`, waits for `listing_live`, then `POST /api/ops/order {task_id, qty}`. `--mode synthetic` posts trend, product, listing (dev2 shape, price 49), an order with cost and an order without cost straight to `/api/events`. Events are contract-valid, mode `mock`, actor `rehearse-dev3`. `--hub` or `HUB_URL` sets the hub. |
| `test_helpers.py` | 12 unit tests, no network. They also validate rehearsal events with `departments/lib/events.validate`. |

## Wiring into agent.py (for the Claude Code bot)

```python
try:
    import grok, qa_bridge          # dev3/ is on sys.path when run as python dev3/agent.py
except Exception:
    grok = qa_bridge = None
```
- finance, after `out = finance_margin(...)`: if `grok`, set `out["grok"] = grok.margin_summary(out)`. In the under-floor branch, `if qa_bridge: qa_bridge.margin_check(tid, out)`.
- legal, after `out = legal_review(e)`: if `grok`, set `out["grok"] = grok.legal_opinion(e)`. The existing `self.qa(tid, out)` on a flag can become `qa_bridge.legal_check(tid, out, opinion=out.get("grok"))`.
- Note: dev4's gate always sends kind `legal` and `pricing` to the founder, so `legal_check` on every **pass** adds one founder-queue item per trend/product. Keep it to flags unless the founder wants that.
- Event `mode` stays honest: emit `live` only when `out["grok"]["mode"] == "live"`.
