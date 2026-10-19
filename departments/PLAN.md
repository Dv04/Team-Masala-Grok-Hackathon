# dev4 plan: end-to-end automation + dashboard (HR 10, Design 11, Data/ops 12, QA gate 13)

Status: PLAN ONLY, nothing below is built yet. Written 6:40 PM CT Oct 19. Freeze 7:30 PM CT, judging 8:30 PM CT.
Builds on the running service in this folder (port 8810 REST + MCP, event log, qa.check, approvals, webhooks, KPIs).

## 0. What "end-to-end" means here
A loop counts as end-to-end only when **no human has to do anything between the trigger and the finished action**,
unless a rule sends it to the founder. Then the founder clicks once and the rest still runs on its own.

    trigger -> agent step -> QA gate -> pass:     action executes -> done event
                                     -> founder:  approval queue -> Approve: action executes -> done
                                                                 -> Reject: logged -> revise once -> QA again -> 2nd reject: failed (stops)
                                     -> fail:     revise once -> QA again -> 2nd fail: founder queue (existing rule)

"Action executes" means a real side effect on the box, not just a log line:
- `data/outbox/<task_id>.eml`: a real RFC-822 email file. Recipients are fictional fixtures. This is the **sandbox send channel**.
  Real delivery stays off, and only becomes possible later after approval through a test-mode provider.
- `data/published/<task_id>/`: approved design assets plus caption.json. This is the "publish" target, and the dashboard serves it.
- `data/hr/pipeline.json`: the ATS record (candidate -> stage: shortlisted / contacted / rejected).
- `data/tasks.jsonl`: tasks created for any of the 13 depts. Other depts receive them by webhook, or pull them with `GET /api/tasks?dept=`.
Each executed action logs a `done` event with `output.action = {type, path|url, executed_by:"auto"|"founder"}`.

### New piece: the automation engine (`lib/auto.py`)
- It subscribes to `events.HOOKS`. The hook runs inside the HTTP request, so it only **enqueues**; a single worker thread
  does the work, which avoids re-entrancy and recursion.
- It has a **rule table**: event pattern -> handler. It is visible at `GET /api/automation/rules` and on the dashboard, so judges can see *why* each thing happened.
- It is idempotent. Each trigger event's key `(task_id, status, ts)` is stored in `data/auto_seen.json`, so a restart never re-fires it.
- Every event the engine writes has `actor:"auto"` and `parent_id` = the triggering task, so chains are traceable.
- A loop guard stops any chain after 5 hops, with max 1 revise per task.

## 1. Per department

| | HR (10) | Design (11) | Data/ops (12) | QA gate (13) |
|---|---|---|---|---|
| **Trigger (no human)** | (a) an `engineering` or any dept event with `output.kind:"hire_needed"`; (b) `POST /api/inbound/hr` (job post or resume webhook); (c) a task created by Ops | (a) a `sales`/`marketing`/`support` event with `output.kind:"design_request"`; (b) `POST /api/inbound/design`; (c) an Ops task | (a) a scheduler thread every 60 s; (b) a Grok Bot scheduled routine calling `ops.scan` over MCP; (c) every `done`/`failed` event | Every customer- or public-facing output from all 13 depts: our depts call it inline; other depts call `/api/qa/check`, or the engine auto-checks any event with `output.needs_qa:true` |
| **Agent step** | rank candidates (open_recruiter with xAI when keyed, otherwise MOCK keyword ranker) + draft outreach | brand-kit prompts -> images (Grok-MCP when keyed, otherwise MOCK SVGs) + caption | DuckDB SQL over the event log: KPIs + anomaly rules (approval waiting >10 min, task stuck `running` >5 min, dept failure rate >30%, no replies sent while founder away) | deterministic rules (real) + xAI rubric/factuality when keyed |
| **QA gate** | `outbound_email` (first contact -> founder) | `public_post` (contact info / overclaim -> fail) | ops-created tasks are `internal` (pass); digests going to the founder are not gated | is the gate itself; its verdict is a `dept:"qa"` event |
| **Auto action on pass** | write `.eml` to outbox, ATS stage -> `contacted`, `done` | copy assets + caption to `data/published/`, `done` | create a task for the responsible dept (`data/tasks.jsonl` + webhook) + `done`; write `data/digests/<date>.md` each run | emit the verdict; engine routes the result (pass -> executor, fail -> revise, founder -> queue) |
| **Founder path** | Approve -> outbox + ATS executed automatically. Reject -> ATS `rejected`, logged, HR re-drafts once with the founder note; 2nd reject -> `failed` | Approve -> published. Reject -> regenerate once using the note as the brief, then stop | n/a, except when an anomaly implies money/pricing: that task is gated `founder` | the founder's decision is the final gate; a second fail always goes to the founder |
| **Logged** | queued/running/qa/needs_approval/approved/done + action path | same + asset paths | scan run, anomalies found, tasks created (with `for_dept`) | verdict, score, reasons, check list, mode |

### Cross-dept chains (rules in the table, demoable)
1. **Engineering "hire needed" -> HR**: event `{dept:"engineering", output:{kind:"hire_needed", role, job_text}}` -> HR run -> QA -> founder (first contact) -> Approve -> outbox `.eml` + ATS.
2. **Sales/Marketing "design request" -> Design**: `{output:{kind:"design_request", brand, brief}}` -> Design run -> QA `public_post` -> pass -> published (or fail -> revise once).
3. **Data/ops anomaly -> task for any dept**: e.g. support has a reply stuck `needs_approval` for 10 min -> Ops creates a `support` task "nudge founder / escalate" and fires support's webhook; failure spike in design -> Ops re-queues the design run.
4. **QA for all 13**: any dept posting `output.needs_qa:true` + `output.content` + `output.kind` is auto-checked, and the verdict webhook goes back to it. dev2's Sales/Support/Engineering use this or `/api/qa/check` directly.
5. **Founder away**: when away is on, pass-path actions keep executing, founder-path items queue up, and Ops writes a "while you were away" digest when away flips off. That digest is the "close the laptop" story.

## 2. Dashboard (`GET /dashboard`, one HTML file served by 8810, no build step)
- **Live updates**: poll `/api/events?limit=50`, `/api/approvals?pending=true`, `/api/ops/kpis` and `/health` every 2 s. SSE is nice-to-have.
- **Dept tiles (13)**: name, owner (dev1-4), last status + time, counts by status, **MOCK / LIVE badge** (from event `mode`), grey when no events yet.
- **Live event feed**: newest first, colored by status, shows actor (`auto`, `founder`, `grok-routine`, dev bot) and the parent chain; click opens the output JSON plus a link to the produced file (.eml, published asset).
- **Approval queue**: summary, dept, preview (email body / image / caption), QA reasons, note box, **Approve / Reject**. A click POSTs `/api/approvals/{id}`; the engine then executes, and the feed shows the action within 2 s.
- **KPIs**: tasks by dept/status, pending approvals, avg time-to-done, replies sent while away, actions executed (auto vs founder).
- **Founder-away toggle** (POST `/api/founder/away`), plus a **"Rules" panel** (automation rule table) and **"Run demo scenario"** button (posts the seed triggers).
- **Header**: honest banner "MOCK mode: no XAI_API_KEY" until a key is set; sandbox notice "emails go to outbox files, not real inboxes".

## 3. Grok Bot use (20% of the score, made visible)
- **Routines as schedulers**: a Grok Bot scheduled routine (every 10-15 min) that calls `ops.scan` / `ops.kpis` on the 8810 MCP endpoint and posts the anomaly digest to PR #2. Events show `actor:"grok-routine"`.
- **Routines as triggers**: a GitHub-triggered routine on PR #2/issues. When a "hire needed" or "design request" comment lands, it posts the event to `/api/events`, which starts the chain.
- **MCP endpoint as tools**: `http://<domain>/mcp` exposes `qa.check, events.append, ops.kpis, ops.scan, approvals.pending, approvals.decide, hr.run, design.run, tasks.create`. Teammates' Bots (and a fresh bot) use it with no human, which also serves the "bot is the user" angle.
- **Bot team visible in the build**: the dashboard feed labels every actor (auto, routine, dev bots, founder).
- Fallback until a public URL exists: routines owned by Dhi's bot run on this same box and can reach `127.0.0.1:8810` from the shell. This is to be verified, and it is the main dependency risk.

## 4. Demo script (3 min)
1. 0:00 Open `/dashboard`: 13 tiles, MOCK badges, empty queue. One line: "a founder of one, 13 bot departments, QA gate on everything."
2. 0:20 Toggle **founder away**, then "close the laptop".
3. 0:30 Trigger chain 1 (Engineering bot / routine posts `hire_needed`) -> feed: HR queued -> running -> QA founder (first contact) -> waiting in queue.
4. 0:55 Trigger chain 2 (Sales posts `design_request`) -> Design -> QA pass -> **published automatically**; open the asset.
5. 1:20 A bad caption (contains an email) -> QA fail -> auto-revise -> pass -> published. Shows the gate working.
6. 1:45 Ops anomaly fires (approval waiting) -> creates a task -> webhook to support (dev2's tile lights up).
7. 2:10 Toggle away off -> "while you were away" digest. Click **Approve** on HR -> `.eml` lands in outbox, ATS updated, feed shows `executed_by: founder`.
8. 2:40 Show the Rules panel + a Grok Bot routine run in the feed + MCP tool list. Close with what's mock vs live.

## 5. Honesty rules
- Every artifact and event carries `mode`; mock files are named `*.MOCK.*` and the dashboard shows MOCK badges. Never call mock output AI-generated.
- No fake claims: report only checks actually run (smoke results printed, not asserted).
- No secrets in the repo or log (events already refuse key-like strings); the key comes only via env.
- "Send" = outbox file with fictional recipients. Anything to a real person happens only after founder approval and only through a sandbox/test-mode channel. Payments are Stripe test mode only and owned by dev2's depts.

## 6. Risks
- Engine recursion / double-fire -> queue + worker + idempotency file + hop limit.
- Concurrent edits to `server.py` by parallel workers -> each worker owns its own module; one owner wires the routes.
- No public URL -> dev2 and routines can't reach 8810 from outside. Mitigation: same-box routines; Dhi's domain/tunnel.
- Live mode is untested until the key arrives; the demo must work fully in MOCK.
- Time: the dashboard is the biggest single task; keep it to plain HTML + fetch.

## 7. Cut line for the 7:30 PM CT freeze
**Must-have**: automation engine + executors (outbox, publish, ATS, tasks), approve->execute / reject->revise-once,
chains 1-4, inbound endpoint, Ops scheduler + anomaly->task, dashboard (tiles, feed, queue with working buttons, KPIs,
away toggle, badges), demo seed script, extended smoke test, 1 Grok Bot routine wired, code on branch `dev4`.
**Nice-to-have**: combined features (section 8), SSE, rules panel polish, "while away" digest, live xAI run, public domain, promptfoo, real sandbox email provider (e.g. a test inbox), Stripe test-mode hookup.

## 8. Combined features (NICE-TO-HAVE, only after full automation + dashboard are done)
Each dept keeps its primary repo, and extra features from other scouted repos sit **behind the same dept endpoint**
(`/api/<dept>/run` or the matching MCP tool), so callers don't change. Each extra is about 10-15 min, adds a field to `output`,
gets its own MOCK/LIVE flag, and is credited in README (license noted). Code is only copied from permissively licensed repos.
Source reports: `/workspace/hackathon-2026/repo-scout/1{0,1,2,3}-*.md`.

| Dept | Primary (kept) | Extra feature | Repo · license | How it plugs in |
|---|---|---|---|---|
| HR 10 | open_recruiter MCP (MIT) | **JD writer + 30/60/90 onboarding plan** | zubair-trabzada/ai-recruiter-claude · MIT | load `recruit-job` / `recruit-onboard` SKILL.md as prompt templates. `hr/run` with `kind:"hire_needed"` writes a JD first; on founder **Approve** of the hire, the executor also writes `data/hr/onboarding/<task>.md`. Template-filled MOCK without a key, Grok with a key |
| HR 10 | | **Blind screening + interview kit** | Ismail-2001/agent-recruiter · MIT | `blind:true` strips names/emails/schools before ranking (fairness flag in output); interview questions per shortlisted candidate. Live: `agent-recruiter screen` CLI with `OPENAI_BASE_URL=https://api.x.ai/v1` (installed from git, verified `--help`). Mock: fixed question bank |
| Design 11 | Grok-MCP + imagegen-skills brandkit (MIT) | **Generate -> score -> retry on-brand loop** | google/adk-recipes on-brand-genmedia · Apache-2.0 (pattern only, no GCP) | after images, score each against the brief (live: Grok-MCP `chat_with_vision`; mock: rule check of palette/caption/size) and regenerate once if below 0.7; scores shown on the dashboard |
| Design 11 | | **Org chart / wireframe board** | yctimlin/mcp_excalidraw · MIT | `design/run` with `asset:"org_chart"` calls `npx -y mcp-excalidraw-server` (no key) to draw the 13-dept company, export `.excalidraw` and a PNG into `design-out/`, then publish. Node v20 compatibility unverified; fall back to `npx -p node@22` like promptfoo |
| Data/ops 12 | mcp-server-motherduck (MIT) | **Read-only SQL gateway + web workbench** | bytebase/dbhub · MIT | snapshot events into SQLite each scan, then `npx -p node@22 @bytebase/dbhub --transport http --port 8080 --readonly --dsn sqlite:///data/events.db`. Safe read-only tool for outside bots (DuckDB stays read-write internal); workbench link on the dashboard. Needs Node ≥22.5 (box has v20) |
| Data/ops 12 | | **Governed metrics / NL questions** | Canner/WrenAI · Apache-2.0 (concept: semantic layer, not the engine) | `data/metrics.yaml` names each KPI with its SQL. New `ops.ask` (MCP + `/api/ops/ask`): live = Grok picks a metric or writes SQL restricted to the `events` view; mock = keyword match to a named metric. The answer cites which metric/SQL ran |
| QA 13 | own rule gate + promptfoo MCP (MIT) | **Second judge: hallucination + correctness prompts** | langchain-ai/openevals · MIT | when keyed, `qa.check` also runs openevals `HALLUCINATION_PROMPT` against `context`; score = min(rules, rubric, openevals). Without a key: `"skipped (no XAI_API_KEY)"` |
| QA 13 | (primary repo extension) | **Golden regression suite / reliability tile** | promptfoo · MIT (deterministic asserts: `contains`, `regex`, `is-json`, `javascript`, no key) | `qa/golden.yaml` holds ~15 known-good and known-bad outputs, and promptfoo eval runs them against `/api/qa/check`. The pass rate shows as a "QA reliability" tile, which proves the gate itself is tested |
