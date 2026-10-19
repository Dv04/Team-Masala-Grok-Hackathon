# Dev2 tasks

Ordered checklist for [plan.md](plan.md). Items are small enough to verify on their own.

## Phase 0 — Plan

- [x] Write `plan.md` (bots, contract, adapters, QA flow, tests, demo, mock/live switch, risks, freeze order).
- [x] Write `task.md` and keep it updated as work lands.

## Phase 1 — Scaffold

- [ ] Add `package.json`, `tsconfig.json`, `vitest.config.ts`, and `.env.example` with no secrets.
- [ ] Extend `.gitignore` so runtime `data/` is not committed.
- [ ] Add shared types: depts `sales|support|engineering`, event statuses, QA kinds, `hire_needed`, `design_request`.
- [ ] Add port guard refusing 8000, 3100, 8790, 8792, and 8810. One listen port, default `8811`, for the mock contract, tools, and webhook.

## Phase 2 — Mock departments service

- [ ] In-memory event log: `POST /api/events` and `GET /api/events` with task, dept, status, and limit filters.
- [ ] Reject bad dept, status, or mode. Force stored `mode` to `mock` on this server. Redact PII in stored output.
- [ ] QA rules on `POST /api/qa/check`: pass, fail, founder, second-fail, PII, public email/phone, placeholder, empty/invalid JSON.
- [ ] Auto QA when `output.needs_qa` is true; webhook the verdict (`actor: qa`, `output.decision`).
- [ ] Approvals, founder-away, KPIs, and webhook registration.
- [ ] Ops sweep (60s timer plus `POST /api/ops/sweep`) and `GET /api/tasks?dept=`.
- [ ] Allow `hire_needed` only from engineering and `design_request` only from sales or support.
- [ ] MCP on the mock: `qa.check`, `events.append`, `ops.kpis`, `approvals.pending`.

## Phase 3 — Shared client and send gate

- [ ] `DepartmentClient`: append event, register webhook, poll events, poll `GET /api/tasks?dept=`.
- [ ] Wait for QA and founder decisions via the inbound webhook store, then poll as fallback.
- [ ] `runCustomerGate`: pass sends once; one revision; second fail or founder waits; rejected does not send.
- [ ] Tests for pass, fail-then-founder, approve, and reject.

## Phase 4 — Sales bot

- [ ] Mock adapters: OpenOutreach `find` only, Reacher, Twenty REST, Warmbly enroll-after-approval. Live mode errors if unset.
- [ ] CRM sheet (JSON + CSV) with fictional `@*.example` contacts.
- [ ] `sales.find_leads` and `sales.draft_outreach` (`design_request` + first-contact email through the gate).
- [ ] Tests: events and `mode`, no raw email in the event log, no send before approval.

## Phase 5 — Support bot

- [ ] Inbox fixture, FAQ file, mock Chatwoot, Inbox Zero, and RAGFlow adapters.
- [ ] `support.triage` and `support.draft_reply` (grounded reply, refund/pricing to founder, FAQ draft, `design_request`).
- [ ] Tests for a QA pass reply and a founder-gated refund.

## Phase 6 — Engineering bot

- [ ] Issue fixture and mock OpenHands + GitHub adapters.
- [ ] `eng.plan_issue` status flow `queued → running → done`, plus `output.kind: hire_needed`.
- [ ] Test the status flow and the hiring event.

## Phase 7 — One service surface

- [ ] One HTTP server. `POST /api/webhooks/inbound` on port `8811` receives QA verdicts, founder decisions, and Ops tasks, and routes them by `dept`.
- [ ] Internal modules poll `GET /api/tasks?dept=` when the webhook did not deliver.
- [ ] One REST surface for all five tools.
- [ ] One streamable-HTTP MCP endpoint, `POST /mcp`, exposing `sales.find_leads`, `sales.draft_outreach`, `support.triage`, `support.draft_reply`, and `eng.plan_issue`.
- [ ] Cross-domain: support bug → `eng.plan_issue`; sales lead question → support FAQ; `hire_needed` and `design_request` events keep the emitting dept.
- [ ] One test suite covers MCP `initialize` / `tools/list` / `tools/call`, the webhook, and the Ops poll fallback.

## Phase 8 — Demo, docs, PR

- [ ] One command, `npm run demo`, runs all three modules in-process, approves the gated email, and prints the event log.
- [ ] README section: how to run, env vars, switch to dev4, contract map, single webhook path and port.
- [ ] `npm test` passes.
- [ ] Commit on `dev2`, push only `dev2`, open PR into `main`, do not merge.
