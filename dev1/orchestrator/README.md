# Orchestrator / Chief of Staff (`dev1/orchestrator`)

Department string: `orchestrator`. It takes a founder request, decomposes it, routes tasks through the shared department service on port **8810**, and posts its own events so the dashboard tile shows connected.

Mock mode is the default. A real model call happens only when `XAI_API_KEY` is set, and that call goes only to `https://api.x.ai/v1` (`GROK_TEXT_MODEL`, else `GROK_FAST_MODEL`, else `grok-4`). No penalty or stop parameters are sent. HTTP uses `httpx` when it is installed, otherwise the stdlib client, still aimed at that host.

## Run

```bash
# dept service first (from departments/)
./start.sh

# CLI
python3 orchestrator.py request "research the market and draft a sales note"
python3 orchestrator.py pulse "Launch something on what's trending today"
python3 orchestrator.py serve            # http://127.0.0.1:8820
```

`ORCH_PORT` (default **8820**) and `DEPT_SERVICE_URL` (default `http://127.0.0.1:8810`) override the ports. This process does not bind 8810, 8000, 3100, 8792, 8790, 8791, or 8899.

HTTP: `GET /health`, `POST /request {"text"}`, `POST /pulse {"text"}`, `GET /status/<request_id>?refresh=1`, `POST /reconcile/<request_id>`.

## What it does

- **General request.** Structured plan, then `POST /api/tasks` for each dept (`for_dept`, `parent_id` = the request id, `actor` `dev1-orchestrator`). Caps: 6 tasks and 3 model calls per request (`--max-tasks`).
- **Needs approval.** Tasks that touch contracts, payment, pricing, or refunds are marked `needs_approval` and still routed. Sibling tasks are not held.
- **Retry.** A routed task whose latest event is `failed` is reassigned once to the same dept. Not twice.
- **Stalls.** An integrations `chain_stalled` event is recorded as orchestrator `output.kind=stall_noted`. This process does not emit `chain_stalled`.
- **Pulse Studio.** `pulse` (or a trending / Pulse request) calls `POST /api/pulse/start` and routes **one research task** whose detail asks research to emit `trend_spotted` `{trend, why, source: "x"}`. Design, QA, legal, listing, marketing, ops, and finance are not routed again: that chain drives itself, and dev4 stand-ins cover a quiet step. Marketing's webhook `http://127.0.0.1:8899/pulse` is not bound here.
- **Events.** `POST /api/events` with `dept: orchestrator`, `actor: dev1-orchestrator`, `mode: live|mock`, status in `queued|running|needs_approval|approved|rejected|done|failed`. Summaries are scrubbed of secrets and contact strings.

`mode` is `live` only when the plan actually came back from xAI. Otherwise it is `mock`.

## Tests

From this folder:

```bash
python -m unittest discover -s tests
```

`python3 smoke.py` (or `./smoke.sh`) hits a running department service on port 8810.

## Contract note

`POST /api/pulse/start` with no `trend` makes the department service emit research `trend_spotted` from its backup list (`source: backup`). That event is the chain trigger: design, QA, listing, marketing, order, and finance follow on their own. This orchestrator also files one research task so a live trend bot can emit its own `trend_spotted` (`source: x`). It does not route those later steps. A 404 from `/api/pulse/start` is recorded as unavailable; the research task is still created. Integrations `chain_stalled` is observed and not re-posted.
