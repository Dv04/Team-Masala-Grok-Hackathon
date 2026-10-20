# Team Masala - Grok Bot Austin Hackathon

Fresh start on Oct 19, 2026. Previous starter preserved on branch `pre-reset-backup`.

Team comms live on PR #2 (draft, do not merge).

Rules: never commit API keys or secrets; label mock output as mock.

## departments/

`departments/` is Pulse Studio, the trend-to-product brand: event log, automation engine, QA approval gate, approvals, webhooks, Ops scheduler, and the department chain (including finance, legal, and integrations). The founder dashboard is `GET /dashboard`. The store is `GET /store`. Every department plugs into this one service.

Run it (port is `DEPT_PORT`, default `8810`):

```bash
python3 -m venv .venv
.venv/bin/pip install -r departments/requirements.txt
DEPT_PORT=8810 .venv/bin/python departments/server.py
```

`GET /health`, `GET /dashboard`, and `GET /store` should return 200. A department posts work with `POST /api/events` (include its `dept` name) and can subscribe with `POST /api/webhooks`. Start a product run with `POST /api/pulse/start`. `departments/start.sh` can also start optional external MCP servers (DuckDB, open_recruiter, promptfoo); those are not required to boot the service. Without `XAI_API_KEY`, HR and Design stay in mock mode and QA runs rules only. Do not commit `.env`, `.venv/`, or `data/*.jsonl` logs.

## Dev2 (Sales, Support, Engineering)

One process on port `8811` (not 8000, 3100, 8790, 8792, or 8810). It posts to the departments service above and embeds `GET /panel` for the three teams. The company dashboard stays at `GET /dashboard` on the departments port.

```bash
npm install
DEPT_PORT=8810 python3 departments/server.py
DEPARTMENTS_BASE_URL=http://127.0.0.1:8810 DASHBOARD_BASE_URL=http://127.0.0.1:8810 npm run dev
```

`npm test` runs the in-process mock. It does not contact port 8810. `npm run demo` runs the mock chains on 8811.

Live suites (`tests/departments-live.test.ts`, `tests/verify-live.test.ts`) register webhooks, post founder approvals, publish a listing, and can call live Grok against the departments service. They run only when `RUN_LIVE=1`. A reachable `http://127.0.0.1:8810/health` does not turn them on. With the flag set, and when that health check reports `service: dev4-departments`, they register `sales`, `support`, and `engineering` with `POST /api/webhooks` and check that their events show up for the dashboard tiles.

```bash
RUN_LIVE=1 npx vitest run tests/departments-live.test.ts tests/verify-live.test.ts
```

Pulse Studio is `POST /api/chains/launch`: a `product_created` event, a QA-checked landing page at `GET /pulse`, a sales event with `output.kind: listing_live`, and a support reply to a buyer. Each step keeps `parent_id`.

Grok stays labeled `MOCK` until the demo host has a real key. Set these for live copy (token prices below are estimates for `grok-4.3` short context and can be overridden with `XAI_PRICE_INPUT_PER_M`, `XAI_PRICE_CACHED_PER_M`, and `XAI_PRICE_OUTPUT_PER_M`):

```bash
XAI_API_KEY=xai-...
XAI_BUDGET_USD=2
XAI_MODEL=grok-4.3
XAI_BASE_URL=https://api.x.ai/v1
XAI_MAX_OUTPUT_TOKENS=120
```

`XAI_API_KEY` must start with `xai-`. `XAI_BUDGET_USD` defaults to 2. Once the running total in `data/xai-budget.json` would pass that cap, calls stop and the reply falls back to labeled MOCK. `XAI_BASE_URL` defaults to `https://api.x.ai/v1` so a spend-limit proxy can replace the host.
