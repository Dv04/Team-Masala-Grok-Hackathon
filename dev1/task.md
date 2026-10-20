# dev1 tasks

Ordered checklist for [PLAN.md](PLAN.md). Marketing and Orchestrator are **not** this PR.

## M0 — Plan (this PR)

- [x] `dev1/PLAN.md` covers Pulse Studio depts 1–3, the `trend_spotted` contract (`trend`, `why`, `source: "x"`), backup trend, honest `mode`, 8s stand-ins, marketing webhook `:8899/pulse`, and how to run.
- [x] `dev1/task.md` lists all three components and names the other PRs.

## M1 — Shared client `dev1/common/` (this PR)

- [x] Text calls use fixed `https://api.x.ai/v1`. `GROK_TEXT_MODEL` and `GROK_FAST_MODEL` default `grok-4`. `GROK_IMAGE_MODEL` defaults `grok-imagine-image-2.0`. Names must start with `grok-`.
- [x] `GrokClient.respond` uses httpx against that host with caller-supplied tools. Mock (no HTTP) when `XAI_API_KEY` is absent. Does not send `stop` or presence/frequency penalties.
- [x] A unit test scans `dev1/` and fails on another provider's model prefix or API host.
- [x] `EventsClient.post_event` POSTs `/api/events`, omits `ts`, and will not send `mode: "live"` without a key.
- [x] Offline tests in `dev1/common/test_offline.py`.

## M2 — Trend bot `dev1/trend_bot/` (this PR) — demo critical path

Acceptance: one command posts dept `research`, status `done`, `output.kind=trend_spotted`, `output.source="x"`, and `output.trend` / `output.why` from Grok when a key works, otherwise from `fixtures/backup_trend.json` with `mode=mock` and `output.fallback=backup_fixture`. No PII. Research dashboard tile has an event.

- [x] Stored backup trend fixture (sticker / tee / poster, no prices, no contact info).
- [x] Live path: Grok `x_search` + `web_search`, JSON `trend` + `why`.
- [x] Failed or missing Grok falls back to the fixture and stays `mock`.
- [x] Offline tests in `dev1/trend_bot/test_offline.py`.
- [x] `python3 -m trend_bot` and `python3 trend_bot/smoke.py` against `DEPARTMENTS_BASE_URL`.

## M3 — Marketing bot `dev1/marketing_bot/` (other PR, not this branch)

Owner: the marketing cloud agent. Do not implement here.

- [ ] On `trend_spotted`, emit `output.kind=design_request` with `brand` and `brief` so Design → QA → publish runs.
- [ ] Listen at `http://127.0.0.1:8899/pulse` (port 8899 is reserved).
- [ ] On product-live / `listing_live`, draft post, blog, and landing copy. `output.needs_qa=true`. Draft only, no live posting.
- [ ] QA: pass → log `done`; fail → revise once and re-check; founder → `needs_approval` and wait.
- [ ] Brand voice file and one skill per content type. Public copy has no email, phone, or price wording that the gate sends to the founder.
- [ ] Post at least one `dept=marketing` event so that dashboard tile leaves "not connected" before dev4's ~8s stand-in.

## M4 — Orchestrator `dev1/orchestrator/` (other PR, not this branch)

Owner: the orchestrator cloud agent. Do not implement here.

- [ ] Decompose a founder request and route by dept name.
- [ ] Track status with `GET /api/events` (webhooks do not fire for ordinary `done`).
- [ ] Retries, budget cap, optional founder hold, and stall handling next to dev3 `chain_stalled`.
- [ ] Direct agent-to-agent messages, mirrored onto the bus.
- [ ] Post at least one `dept=orchestrator` event so that dashboard tile leaves "not connected" before dev4's ~8s stand-in.

## M5 — Live rehearsal (when a key exists)

- [ ] `XAI_API_KEY=... python3 -m trend_bot` returns `mode=live` and a trend that is not the fixture, or the real error is reported and the event stays `mock`.
