# Dev2 plan — Sales, Support, and Engineering bots

Team Masala, Grok Bot hackathon (Oct 19, 2026). Code freeze is about 7:30 PM CT. Judges visit at 8:30. This branch (`dev2`) owns departments 4–6. `main` stays untouched; this work lands only through a PR from `dev2`. Research write-ups stay on `research/dev2` and are not copied here.

## Goal

Ship three department bots that do a real, demo-able job against dev4’s shared contract:

- **Sales** builds a lead list for a described customer, drafts first-touch outreach, and keeps a local CRM sheet.
- **Support** triages a sample inbox, drafts replies grounded in a small FAQ, and files new FAQ drafts.
- **Engineering** turns a GitHub issue (or a fixture) into a task plan and a status trail, and emits a hiring signal when the issue needs another person.

Reliability beats extra tools. External products run through adapters that default to **mock**. Event `mode` is always `mock` until both the departments service and the tool adapters are actually live.

## Contract (dev4, including the cross-dept update)

Departments service base URL comes from **`DEPARTMENTS_BASE_URL`**. The demo and tests point it at the local mock. Switching to dev4’s service (their process listens on port **8810**; the public host is not posted yet) is that one variable. Tool adapters stay mocked until `TOOLS_MODE=live` and each tool URL is set.

`dept` is exactly `sales`, `support`, or `engineering`.

Every action is appended with `POST /api/events` (never by writing `data/events.jsonl`). Fields: `ts`, `dept`, `task_id`, `parent_id`, `actor`, `status` (`queued | running | needs_approval | approved | rejected | done | failed`), `summary`, `output`, `needs_approval`, `mode` (`live | mock`, required and honest). No secrets or raw PII in stored `output`.

QA:

- Explicit check: `POST /api/qa/check` and MCP tool `qa.check`. Body `{dept, task_id, kind, content, context}`. Kind includes `customer_reply | outbound_email | refund | payment | public_post | internal`, plus founder kinds `discount | legal | pricing`.
- Response `{verdict: pass|fail|founder, score, reasons, checks}`.
- `pass` → send, then log `done` with `output.kind` and `sent: true` for a real customer send.
- `fail` → revise **once** using `reasons`, check again. A second failure on the same `task_id` becomes `founder`.
- `founder` → log `needs_approval`, do **not** send. Wait for the founder webhook or `GET /api/events?task_id=X&status=approved`. Send only after `approved`. `rejected` means not sent.
- Founder is required for refunds, payments, discounts, legal, pricing changes, any outbound email unless `context.first_contact` is `false`, score `< 0.7`, and a second failure.
- QA fails on PII (card, SSN, API keys), email or phone in a `public_post`, placeholder text, and empty or invalid JSON.
- Payments are Stripe **test** mode only (recorded on the event; no live charge).

Auto QA (new): an event with `output.needs_qa: true` is QA-checked by the departments service. The verdict is stored as an event with `actor: "qa"` and `output.decision`, and POSTed to the department webhook. Founder decisions use `actor: "founder"`. Callers tell them apart by `actor` and `output.decision`.

Cross-dept `output.kind` values (new):

- `hire_needed` — emitted only by **engineering**. Dev4’s HR chain ranks candidates and drafts outreach; founder still approves that first contact. This bot does not email candidates.
- `design_request` — emitted only by **sales** or **support**. Dev4’s Design chain builds a brand asset and caption and auto-publishes on QA pass. The caption is submitted with `needs_qa: true` and checked as a public post (no email or phone).

Ops (new): the departments service sweeps about every 60 seconds. Stuck or failed department work becomes a task delivered two ways:

- webhook POST to this bot
- `GET /api/tasks?dept=<dept>` which the bots poll as a fallback

Webhook registration on the departments service remains `POST /api/webhooks` with `{url, dept}` (best effort, 5s timeout, no retries or signing). Ops KPIs: `GET /api/ops/kpis`. Founder actions: `GET /api/approvals?pending=true` and `POST /api/approvals/{task_id}` with `{decision: approved|rejected, note}`.

## Architecture

One process, one listen port, one shared config. Sales, Support, and Engineering are internal modules. They are not separate servers. Every event they emit still sets `dept` to exactly `sales`, `support`, or `engineering`.

```
Orchestrator / demo / npm test
        |
        v
dev2 service  (default :8811)
  POST /mcp                         all five tools on one streamable-HTTP endpoint
  POST /api/sales/find-leads
  POST /api/sales/draft-outreach
  POST /api/support/triage
  POST /api/support/draft-reply
  POST /api/engineering/plan-issue
  POST /api/webhooks/inbound        one receiver; routed internally by dept
  GET  /api/webhooks/inbound
  GET  /health
  GET  /api/status?dept=            tile status for dev4's dashboard to read
  GET  /panel                       embeddable panel (iframe). Not a second company dashboard.
        |
        |  one DepartmentClient
        |  DEPARTMENTS_BASE_URL for the contract
        |  DASHBOARD_BASE_URL for the company feed (defaults to DEPARTMENTS_BASE_URL)
        v
Departments contract + dev4 dashboard (port 8810, page /dashboard)
  default: the same process mounts the mock contract on :8811
  live:    DEPARTMENTS_BASE_URL points at dev4 (their port 8810; public host TBD)
           and this process keeps serving tools, REST, and the webhook
```

Mock contract routes on the same server (used when the base URL is this process):

- `POST /api/events`, `GET /api/events`
- `POST /api/qa/check`, MCP tools `qa.check`, `events.append`, `ops.kpis`, `approvals.pending` under `POST /mcp/departments` so they do not collide with the bot tool endpoint `POST /mcp`
- `GET /api/ops/kpis`, `GET /api/approvals`, `POST /api/approvals/:task_id`
- `POST /api/webhooks` (registration), `POST /api/founder/away`
- `GET /api/tasks?dept=`
- `POST /api/ops/sweep` (mock-only; tests do not wait 60s)

The single webhook path is **`POST /api/webhooks/inbound`** on **`WEBHOOK_PORT` (default 8811)**. QA verdicts, founder decisions, and Ops tasks all arrive there and are dispatched by `dept`. Forbidden ports: 8000, 3100, 8790, 8792, 8810.

### Cross-domain flows (inside this process)

- A support message that describes a product bug calls `eng.plan_issue` with `parent_id` set to the support task. The support event stays `dept: support`; the plan stays `dept: engineering`.
- A sales lead that includes a product question is looked up in the support FAQ. The answer is stored as support knowledge (`dept: support`) and linked back to the sales task.
- Engineering emits `output.kind: hire_needed`. Sales and Support emit `output.kind: design_request`. Dev4's chains key off those kinds and the exact dept.

`DepartmentClient` appends events, reads QA verdicts (inline mock response, webhook inbox, or poll), waits for founder `approved` / `rejected` the same way, registers the webhook, and polls `GET /api/tasks`. Stored event output is redacted (emails, phones, cards, SSNs, keys). Auto QA runs on the raw body first so a public-post email still fails, then the copy written to the log is redacted.

`runCustomerGate` is the only send path:

1. Log `running` with `output.needs_qa: true`, a `qa_request_id`, `kind`, and `content`.
2. Read the QA verdict.
3. `pass` → `send()`, log `done` with `{kind, sent: true}`.
4. `fail` → revise once, submit a second `needs_qa` event.
5. Second `fail`, or an immediate `founder` → log `needs_approval` and wait. `send()` runs only after `approved`.

Sandbox rule: outreach recipients are fictional `@*.example` addresses. OpenOutreach’s adapter exposes **`find` only** (no `send` / `run`).

## Bots and tools

| Tool | What it does | QA |
|---|---|---|
| `sales.find_leads` | OpenOutreach `find` → Reacher verify → CRM sheet + Twenty upsert | Not customer-facing. Logged only. |
| `sales.draft_outreach` | One `design_request` caption, then a first-touch `outbound_email` per lead (`first_contact: true`) | Design caption is a public-post QA. Email is founder. Warmbly enroll runs only after approval. |
| `support.triage` | Classify the fixture inbox (Chatwoot / Inbox Zero adapters) | Logged only. |
| `support.draft_reply` | RAGFlow-style FAQ lookup, reply or FAQ draft | `customer_reply` may pass. `refund` and `pricing` go to founder. A design ask emits `design_request`. |
| `eng.plan_issue` | GitHub issue → plan + status `queued → running → done`. OpenHands conversation is a stub. | Plan text is `internal`. A staffing signal emits `hire_needed`. |

### Researched repos → adapters

Mocks are the default (`TOOLS_MODE=mock`). Live mode calls the real API and errors if the URL or key is missing. It never invents a successful live response.

| Repo | Bot | How |
|---|---|---|
| Twenty | Sales | REST adapter (`POST /rest/people`). Native MCP exists upstream; we do not proxy it tonight. |
| OpenOutreach | Sales | CLI adapter, **`find` only**. No MCP upstream. |
| Reacher | Sales | REST adapter `POST /v0/check_email`. |
| Warmbly | Sales | REST adapter for sequence enroll after approval. |
| Chatwoot | Support | REST/webhook adapter (no official MCP). |
| Inbox Zero | Support | MCP-shaped adapter (`search_inbox`, `create_draft`). Drafts do not send. |
| RAGFlow | Support | Retrieval adapter over the local FAQ file. Upstream MCP is not required for the demo. |
| OpenHands | Engineering | REST stub (`POST /api/conversations`). Returns a mock conversation id. |
| GitHub MCP / REST | Engineering | Fixture issue in mock mode. Live mode reads one issue when `GITHUB_TOKEN` and `GITHUB_ISSUE` are set. |

Crawl4AI, PR-Agent, Plane, BookStack, and ContextForge stay documented in the research branch. They are not in the demo path.

## Testing

`npm test` runs Vitest in-process (no extra services):

- Every bot action logs an event with a legal status, dept, and `mode: "mock"`.
- QA pass → `sent: true` and `done`.
- QA fail → one revision, then founder on the second failure. Nothing is sent before a decision.
- Founder → `needs_approval`, no send until `approved`.
- `rejected` → not sent.
- `needs_qa: true` produces a QA event and a webhook delivery.
- Ops sweep files a task, webhook delivery works, and `GET /api/tasks?dept=` works as the poll fallback.
- `hire_needed` only from engineering. `design_request` only from sales or support.
- MCP `initialize`, `tools/list`, and `tools/call` for `sales.find_leads`.

`npm run demo` starts the one dev2 service (mock contract included), runs all three modules, approves the founder-gated sales email, prints the event log and KPIs, and exits 0.

## Company dashboard and the dev2 panel

Dev4 owns the one company dashboard at `/dashboard` (port 8810 on their box today). This service does not copy that page.

- Events reach the live feed and the 13 tiles because we `POST /api/events` with `dept` set to `sales`, `support`, or `engineering`, honest `mode`, and `needs_approval` when a founder decision is required. `DASHBOARD_BASE_URL` defaults to `DEPARTMENTS_BASE_URL`. If the two URLs differ, the client also mirrors the stored event to the dashboard so the feed updates, with `needs_qa` removed so QA does not run twice.
- Founder decisions are dev4's queue: `GET /api/approvals` and `POST /api/approvals/{task_id}`. The panel's Approve and Reject buttons call that API (the local mock until their public URL exists).
- On startup we register `POST /api/webhooks` `{url, dept}` for each of the three departments. The URL is `http://<this-host>:8811/api/webhooks/inbound`.
- Dev4 can point a tile at `GET http://<dev2-host>:8811/api/status?dept=sales` (also `support` and `engineering`). `GET /health` returns all three.
- Embed the panel, do not frame their whole dashboard: `<iframe src="http://<dev2-host>:8811/panel" title="Sales, Support, and Engineering"></iframe>`.
- The mock also serves the read shapes their page uses: `GET /api/stream?once=1`, `GET /api/automation/rules`, `GET /api/ops/kpis`, and the approval queue. `GET /dashboard` on this process is only a pointer to their page and to `/panel`.

Their MCP stays at `{DEPARTMENTS_BASE_URL}/mcp` (`qa.check`, `events.append`, `ops.kpis`, `approvals.pending`, plus `approvals.decide` and `automation.rules` when that build is up). Our tool endpoint is `{this service}/mcp` with the five department tools. The mock contract tools are at `/mcp/departments` so the two lists do not collide on one port.

## Mock vs live

| Switch | Effect |
|---|---|
| `DEPARTMENTS_BASE_URL=http://127.0.0.1:8811` | Local mock mounted in this same process (default). |
| `DASHBOARD_BASE_URL` | Defaults to `DEPARTMENTS_BASE_URL`. Set it if the dashboard host differs. |
| `DEPARTMENTS_BASE_URL=<dev4 public URL>` | Same client talks to the live contract and the company queue. This process still serves `/mcp`, `/panel`, `/api/status`, and `/api/webhooks/inbound`. |
| `TOOLS_MODE=mock` | Adapters return fixtures. Event `mode` stays `mock` even if the departments URL is public. |
| `TOOLS_MODE=live` plus tool URLs | Adapters call those services. Event `mode` becomes `live` only when the departments URL is not localhost. |
| `EVENT_MODE=live` while tools are mocked | Ignored. Mock work is not labeled live. |

## Risks

- Dev4’s public base URL may still be missing at demo time. The mock is the path that has to work.
- Dev4 can reach `127.0.0.1:8811` only from the same machine. Another host needs a tunnel. The path stays `/api/webhooks/inbound` and the port stays `8811` unless `WEBHOOK_PORT` is set.
- Live Twenty, Warmbly, Chatwoot, RAGFlow, and OpenHands are not installed tonight. Live mode fails closed.
- Auto QA plus a second manual `qa.check` on the same `task_id` would burn the one allowed failure. The gate uses `needs_qa` only.
- Ops sweep uses a 60s timer. Tests call `POST /api/ops/sweep` so they do not wait.

## Timeline toward the 7:30 PM CT freeze

Work is ordered so a green `npm test` and `npm run demo` exist before the freeze. Live tool installs are out of scope after that. The order is: plan and checklist, one service (contract mock + shared client + three internal modules), one MCP/REST/webhook surface, one test suite, one demo, README, PR into `main` (not merged).
