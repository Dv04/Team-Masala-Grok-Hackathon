# Team Masala — dev4 departments: HR (10), Design (11), Data/ops (12), QA approval gate (13)

Implements the PR #2 inter-department contract plus the additions agreed with dev2 (events API, approvals, webhooks).
Not in the repo yet (will move to branch `dev4` via PR). Without `XAI_API_KEY`, HR and Design return **`mode: mock`**
output and QA runs **rules only**. Nothing mock is ever labeled live.

## Run
```bash
./start.sh          # starts everything, prints /health
.venv/bin/python smoke.py   # 31 checks; writes smoke events
./reset.sh          # archive events.jsonl + webhooks.json to data/archive/ (clean demo state)
./stop.sh
# live mode later: XAI_API_KEY=... ./start.sh   (optional: HR_LLM_MODEL=xai/<model>, QA_MODEL=<model>, WITH_PROMPTFOO=1)
```

## Ports (all bind 127.0.0.1; a public tunnel/domain goes in front later)
| Port | Process | What |
|---|---|---|
| 8810 | `server.py` | dept service: REST below + MCP streamable HTTP at `/mcp` |
| 8000 | `mcp-server-motherduck` | DuckDB MCP at `/mcp`, view `events` over `data/events.jsonl` (tools: execute_query, list_tables, ...) |
| 8792 | `openrecruiter-mcp` | HR engine (LLM_PROVIDER=xai). Only used when XAI_API_KEY is set |
| 3100 | promptfoo MCP | opt-in (`WITH_PROMPTFOO=1`); the gate calls xAI directly for the rubric |
Avoid 8790/8791 (box egress tunnel).

## REST (base http://127.0.0.1:8810)
| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/health` | | modes per dept (live/mock, rules_only) |
| POST | `/api/events` | one event (contract §1) | `{ok, event}` or 400 with reason. **Only this service writes events.jsonl** |
| GET | `/api/events` | `?task_id=&dept=&status=&limit=` | `{events:[...]}` (poll this) |
| POST | `/api/qa/check` | `{dept, task_id, kind, content, context?, first_contact?}` | `{verdict, score, reasons, checks}` (+ `mode`, `check_results`) |
| GET | `/api/ops/kpis` | | tasks per dept by status, pending approvals, avg time-to-done, replies sent while founder away |
| GET | `/api/approvals?pending=true` | | `{pending:[{task_id, dept, summary, since, mode, output}]}` |
| POST | `/api/approvals/{task_id}` | `{decision: approved\|rejected, note}` | appends approved/rejected event (same task_id, dept = originating dept, actor `founder`). 404 if not pending |
| POST/GET | `/api/webhooks` | `{url, dept}` (`dept: "all"` = everything) | registry. These events are POSTed (JSON event) to the hooks of the event's dept (plus `output.for_dept` for qa events) and to `all` hooks: `approved`/`rejected`; `queued` with `output.kind: "task"` (a task routed to a dept); `done` whose `output.action` is an object (an executed action). Best effort, 5 s timeout, results in `logs/webhooks.log` |
| POST | `/api/founder/away` | `{away: true\|false}` | presence event, drives the "replies while away" KPI |
| POST | `/api/hr/run` | `{job_text?, resumes?[], top_k?, parent_id?}` | shortlist + outreach draft, through qa.check |
| POST | `/api/design/run` | `{brand, brief, n_posts? (<=2), caption?, parent_id?}` | logo + posts + caption, through qa.check |

MCP tools at `http://127.0.0.1:8810/mcp`: `qa.check`, `events.append`, `ops.kpis`, `approvals.pending`, `hr.run`, `design.run`.

Statuses (exact): `queued, running, needs_approval, approved, rejected, done, failed`. `mode`: `live|mock`.
Note: the QA gate logs its own verdict as a `dept:"qa"` event on your task_id (pass→`approved`, fail→`rejected`,
founder→`needs_approval`, with `output.for_dept`). Founder decisions are `actor:"founder"` with `output.decision`.
Webhooks for your dept fire for both; check `actor` to tell them apart.

## QA approval rules (deterministic, no key)
- **fail** (revise once, re-check): empty content; invalid JSON when content looks like JSON; SSN / card number (Luhn) / API key;
  email or phone in a `public_post`; placeholder or banned text (`[insert ...]`, TODO, "as an AI language model").
- **founder** (don't send, queued on dashboard): kind `refund|payment|discount|legal|pricing`; `outbound_email` unless
  `first_contact:false` (first message to a new lead); legal wording (guarantee, contract, liability, compensate...); money/pricing
  wording (refund, discount, % off, $ amounts) outside `internal`; score < 0.7; a **second fail on the same task_id**.
- **pass** otherwise. Score starts at 1.0, −0.15 per soft flag (overclaim, contact info in 1:1 reply), −0.5 on hard fail.
- With `XAI_API_KEY`: one xAI call adds rubric + factuality (against `context`) and score = min(rules, LLM). Without: both are
  `"skipped (no XAI_API_KEY)"`, `mode:"rules_only"`.

## For dev2 (Sales / Support / Engineering) — curl
```bash
API=http://127.0.0.1:8810   # replace with the public domain once Dhi sets it up
# 1. log every action
curl -s $API/api/events -H 'content-type: application/json' -d '{"dept":"support","task_id":"t-42","parent_id":"req-7","actor":"dev2-bot","status":"running","summary":"Drafting reply to customer #42","mode":"live","output":{}}'
# 2. check before anything goes to a customer
curl -s $API/api/qa/check -H 'content-type: application/json' -d '{"dept":"support","task_id":"t-42","kind":"customer_reply","content":"Hi! Your order shipped today.","context":"Customer: where is my order?"}'
# 3a. pass -> send, then log done (kind+sent feed the "replies while founder away" KPI)
curl -s $API/api/events -H 'content-type: application/json' -d '{"dept":"support","task_id":"t-42","actor":"dev2-bot","status":"done","summary":"Replied to #42","mode":"live","output":{"kind":"customer_reply","sent":true}}'
# 3b. founder -> log needs_approval and wait; get notified on approve/reject:
curl -s $API/api/webhooks -H 'content-type: application/json' -d '{"url":"https://<your-bot-webhook>","dept":"support"}'
#     or poll:  curl -s "$API/api/events?task_id=t-42&status=approved"
# founder side
curl -s "$API/api/approvals?pending=true"
curl -s $API/api/approvals/t-42 -H 'content-type: application/json' -d '{"decision":"approved","note":"ok"}'
curl -s $API/api/ops/kpis
```
CLI on this box: `bin/emit --dept support --task t-1 --status done --summary "..." --mode mock --output '{"kind":"customer_reply"}'`
(posts to the service; `--local` writes the file directly only if the service is down).
Ad-hoc SQL: DuckDB MCP on :8000, e.g. `SELECT dept, status, count(*) FROM events GROUP BY ALL`.

## What's mock until the xAI key arrives
- HR: offline keyword-overlap ranking on fictional fixtures (`data/fixtures`), template outreach. `engine` says MOCK.
- Design: local SVG placeholders stamped "MOCK ... not AI generated" in `design-out/<task_id>/`; brand-kit prompts are real
  (structure adapted from Leonxlnx/imagegen-skills, MIT) and are what Grok-MCP gets in live mode.
- QA: rubric/factuality skipped; deterministic rules are real.
- Data/ops: fully real.

## Files
`server.py` service · `lib/events.py` schema + locked append · `lib/qa.py` gate · `lib/ops.py` KPI SQL · `lib/depts.py` HR/Design
· `vendor/Grok-MCP` (MIT, merterbak) · `data/` log, webhooks, fixtures, init.sql · `logs/` · `run/*.pid`

## Combined features: credits and licenses (only what is actually in this folder)
| Feature | Where | Source repo (commit) | License | Copied vs reimplemented | Mode now |
|---|---|---|---|---|---|
| X01 JD writer (`output.jd` on every `hire_needed` HR run) | `lib/hr_extras.py` `write_jd` | [zubair-trabzada/ai-recruiter-claude](https://github.com/zubair-trabzada/ai-recruiter-claude) (`vendor/ai-recruiter-claude/COMMIT`) | MIT (`vendor/ai-recruiter-claude/LICENSE`) | `skills/recruit-job/SKILL.md` **copied unmodified** into `vendor/`. The mock template is **our own text**, following that skill's "Rewritten JD" section layout. The live path sends the SKILL.md as the xAI system prompt (**not run yet**, no key) | MOCK |
| X01 30/60/90 onboarding plan (written on founder **Approve** of HR outreach, `data/hr/onboarding/<task>.MOCK.md`, `/files/onboarding/...`) | `lib/hr_extras.py` `onboarding_plan`, `lib/flows.py` | same repo, `skills/recruit-onboard/SKILL.md` (copied unmodified into `vendor/`) | MIT | **Reimplemented**: our own condensed plan using the skill's structure (Day 1 checklist, Week 1 table, 30/60/90 milestones, evaluation criteria). No LLM | MOCK (template) |
| X02 Blind screening (`blind:true`, default on for `hire_needed` chains): names, emails, phones, school names and gendered words are masked before ranking; identity is re-attached only for the outreach greeting; `output.fairness.removed` counts | `lib/hr_extras.py` `blind`, `lib/depts.py` | [Ismail-2001/agent-recruiter](https://github.com/Ismail-2001/agent-recruiter) (`vendor/agent-recruiter/COMMIT`) | MIT (`vendor/agent-recruiter/LICENSE`) | **Reimplemented** from the `BiasMitigator.mask_pii` idea (mask identity before scoring). No code copied; our regex masking goes further than the original, which only masks the name | real masking; ranking is MOCK |
| X02 Interview kit (`output.interview_kit`: questions that verify matched skills and probe gaps, per shortlisted candidate) | `lib/hr_extras.py` `interview_kit` | same repo, `InterviewGeneratorAgent` pattern | MIT | **Reimplemented** pattern. Our own fixed question bank, no LLM | MOCK |
| X07 openevals second judge | `lib/qa.py` (`check_results.openevals`) | langchain-ai/openevals | MIT | **Nothing copied or wired.** It's only a status label: `skipped (no XAI_API_KEY)`. It never affects the score | not active |
