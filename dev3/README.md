# dev3: finance, legal, integrations

Three Pulse Studio departments that plug into the shared hub in `departments/`. They use the same contract as everyone else: read `GET /api/events`, write `POST /api/events`, and route legal flags through `POST /api/qa/check`. Stdlib Python only. No keys, no LLM calls, no extra glue.

| Dept | Consumes | Emits |
|---|---|---|
| finance | `order_placed` (price/cost from the order, or from the parent `listing_live` `product.price_usd/cost_usd`) | `margin_update` {revenue, cogs, payment_fees (Stripe 2.9% + $0.30, test mode), margin, margin_pct}. Under the 25% floor it goes to `needs_approval` (founder queue). A missing price or cost becomes `failed` and is never guessed. |
| legal | `trend_spotted`, `product_created` | `legal_review` pass, or a flag (protected marks, real-person likeness, POD/Stripe ToS words). A flag goes to `needs_approval` and also to `qa.check` kind `legal`, which sends it to the founder. Rules pre-check only, not a trademark database search. |
| integrations | every event | `dept_online` x3 at start, `connection_map` (13 depts: connected, last status, age), `chain_stalled` when a hop in trend_spotted -> product_created -> listing_live -> order_placed -> margin_update is missing for 120s, and `chain_complete`. |

## Run

```bash
cd departments && ./start.sh          # or: python server.py   (hub on :8810)
python dev3/agent.py                  # polls every 3s; HUB=http://host:8810 to point elsewhere
python -m unittest dev3/test_agent.py # 11 tests, no hub needed
```

Env: `HUB`, `DEV3_POLL_SEC` (3), `DEV3_STALL_SEC` (120), `DEV3_MARGIN_FLOOR` (0.25), `DEV3_SEEN` (dedupe file, default `dev3/.seen.json`).
Polling instead of webhooks is deliberate: it needs no public URL. The box tunnel is blocked, and the hub only fans webhooks out for queued tasks, approvals and done-with-action events.
