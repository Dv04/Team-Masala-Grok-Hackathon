# Dev2 tasks

Ordered checklist for [plan.md](plan.md). Items are small enough to verify on their own.

## Phase 0 — Plan

- [x] Write `plan.md` (bots, contract, adapters, QA flow, tests, demo, mock/live switch, risks, freeze order).
- [x] Write `task.md` and keep it updated as work lands.

## Phase 1 — Scaffold

- [x] Add `package.json`, `tsconfig.json`, `vitest.config.ts`, and `.env.example` with no secrets.
- [x] Extend `.gitignore` so runtime `data/` is not committed.
- [x] Add shared types: depts `sales|support|engineering`, event statuses, QA kinds, `hire_needed`, `design_request`.
- [x] Add port guard refusing 8000, 3100, 8790, 8792, and 8810. One listen port, default `8811`, for the mock contract, tools, and webhook.

## Phase 2 — Mock departments service

- [x] In-memory event log: `POST /api/events` and `GET /api/events` with task, dept, status, and limit filters.
- [x] Reject bad dept, status, or mode. Force stored `mode` to `mock` on this server. Redact PII in stored output.
- [x] QA rules on `POST /api/qa/check`: pass, fail, founder, second-fail, PII, public email/phone, placeholder, empty/invalid JSON.
- [x] Auto QA when `output.needs_qa` is true; webhook the verdict (`actor: qa`, `output.decision`).
- [x] Approvals, founder-away, KPIs, and webhook registration.
- [x] Ops sweep (60s timer plus `POST /api/ops/sweep`) and `GET /api/tasks?dept=`.
- [x] Allow `hire_needed` only from engineering and `design_request` only from sales or support.
- [x] MCP on the mock: `qa.check`, `events.append`, `ops.kpis`, `approvals.pending`.

## Phase 3 — Shared client and send gate

- [x] `DepartmentClient`: append event, register webhook, poll events, poll `GET /api/tasks?dept=`.
- [x] Wait for QA and founder decisions via the inbound webhook store, then poll as fallback.
- [x] `runCustomerGate`: pass sends once; one revision; second fail or founder waits; rejected does not send.
- [x] Tests for pass, fail-then-founder, approve, and reject.

## Phase 4 — Sales bot

- [x] Mock adapters: OpenOutreach `find` only, Reacher, Twenty REST, Warmbly enroll-after-approval. Live mode errors if unset.
- [x] CRM sheet (JSON + CSV) with fictional `@*.example` contacts.
- [x] `sales.find_leads` and `sales.draft_outreach` (`design_request` + first-contact email through the gate).
- [x] Tests: events and `mode`, no raw email in the event log, no send before approval.

## Phase 5 — Support bot

- [x] Inbox fixture, FAQ file, mock Chatwoot, Inbox Zero, and RAGFlow adapters.
- [x] `support.triage` and `support.draft_reply` (grounded reply, refund/pricing to founder, FAQ draft, `design_request`).
- [x] Tests for a QA pass reply and a founder-gated refund.

## Phase 6 — Engineering bot

- [x] Issue fixture and mock OpenHands + GitHub adapters.
- [x] `eng.plan_issue` status flow `queued → running → done`, plus `output.kind: hire_needed`.
- [x] Test the status flow and the hiring event.

## Phase 7 — One service surface

- [x] One HTTP server. `POST /api/webhooks/inbound` on port `8811` receives QA verdicts, founder decisions, and Ops tasks, and routes them by `dept`.
- [x] Internal modules poll `GET /api/tasks?dept=` when the webhook did not deliver.
- [x] One REST surface for all five tools.
- [x] One streamable-HTTP MCP endpoint, `POST /mcp`, exposing `sales.find_leads`, `sales.draft_outreach`, `support.triage`, `support.draft_reply`, and `eng.plan_issue`.
- [x] Cross-domain: support bug → `eng.plan_issue`; sales lead question → support FAQ; `hire_needed` and `design_request` events keep the emitting dept.
- [x] One test suite covers MCP `initialize` / `tools/list` / `tools/call`, the webhook, and the Ops poll fallback.

## Phase 7b — Dashboard feed and embeddable panel

- [x] `DASHBOARD_BASE_URL` defaults to `DEPARTMENTS_BASE_URL`. Events posted for the contract also show on the feed. A different dashboard URL gets a mirror copy without a second QA run.
- [x] `GET /api/status?dept=` and `GET /health` for the three tiles. Mock `GET /api/stream` and `GET /api/automation/rules`.
- [x] Register `POST /api/webhooks` for `sales`, `support`, and `engineering` on startup.
- [x] Serve `GET /panel`: three department cards, prefilled Try it actions, plain-language timeline, Approve/Reject sent to the shared queue, MOCK/LIVE badge, empty states, keyboard and contrast. Iframe-friendly. No second company dashboard.
- [x] Test the status tile, the stream, and that `/panel` renders the three departments.

## Phase 8 — Demo, docs, PR

- [x] One command, `npm run demo`, runs all three modules in-process, approves the gated email, and prints the event log.
- [x] README section: how to run, env vars, switch to dev4, contract map, single webhook path and port.
- [x] `npm test` passes.
- [x] Commit on `dev2`, push only `dev2`, open PR into `main`, do not merge.
- [x] Pulse Studio launch: `product_created`, QA-checked landing page, `output.kind: listing_live`, support answers the buyer, linked by `parent_id`.
