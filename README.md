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

`npm test` runs the in-process mock. If `http://127.0.0.1:8810/health` reports `service: dev4-departments`, the live test also registers `sales`, `support`, and `engineering` with `POST /api/webhooks` and checks that their events show up for the dashboard tiles. `npm run demo` runs the mock chains on 8811.

Pulse Studio is `POST /api/chains/launch`: a `product_created` event, a QA-checked landing page at `GET /pulse`, a sales event with `output.kind: listing_live`, and a support reply to a buyer. Each step keeps `parent_id`.
