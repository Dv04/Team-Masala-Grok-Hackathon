# Internal interfaces (W1, 6:50 PM CT). Owner of server.py: W1. Don't edit server.py; ship a module.

## Plugging a module into server.py
server.py does, at import time, guarded with try/except (a missing/broken module never breaks startup):
    import inbound; inbound.register(mcp)   # lib/inbound.py  (W3, T05)
    import sched;   sched.register(mcp)     # lib/sched.py    (W3, T06) start your thread inside register()
    import chains;  chains.register(mcp)    # lib/chains.py   (W3, T04) register rules inside register()
`mcp` is the FastMCP app: add REST with `@mcp.custom_route("/api/x", methods=["GET"])` (async fn(req) -> JSONResponse)
and MCP tools with `@mcp.tool(name="ops.scan")`. Import errors are logged to logs/dept-service.log as `MODULE <name> FAILED`.
lib/ is on sys.path, so `import events, auto, actions, depts, qa, ops`.

## Automation engine: lib/auto.py
- `auto.rule(name, when, then, match, handle, source="chains.py", once_per_task=True)`; register or REPLACE by name.
  `match(ev) -> bool` must be cheap and pure; `handle(ev)` does the work in the single engine worker thread (it may call
  depts.hr_run / depts.design_run / qa.check / actions.* / auto.emit). Don't block for long; never call HTTP on 8810 from a handler.
  once_per_task=True means it fires at most once per (rule, ev.task_id); False means once per trigger event (task_id,status,ts).
  Dedupe keys persist in data/auto_seen.json. Hop guard: if the trigger task is >=5 parent_id hops deep, it is not fired (failed event).
- `auto.emit(dept, task_id, status, summary, mode, output=None, parent_id=None, needs_approval=None)` writes an event with actor="auto".
  Events from ANY source (REST /api/events, MCP events.append, depts, engine) go through events.HOOKS -> the engine queue,
  so emitting an event IS how you trigger other rules.
- `auto.list_rules()` is what GET /api/automation/rules returns: `{"rules":[{name,when,then,source,once_per_task}]}`.
- Built-in rules (lib/flows.py), names you can rely on:
  chain.hire_needed->hr, chain.design_request->design, exec.hr_on_pass, exec.design_on_pass,
  founder.approve->execute, founder.reject->revise_once.
  So W3's chains.py should ADD: `chain.needs_qa->qa` (any event output.needs_qa:true) and `chain.ops_task->dept`.
  Chains 1+2 already exist; don't re-register them under different names (would double-fire).

## Executors: lib/actions.py (each returns an `action` dict {type, path, url, executed_by, ...})
- `actions.outbox_email(task_id, to_name, subject, body, mode, executed_by)` -> data/outbox/<task>[.MOCK].eml (fictional @example.com)
- `actions.publish_design(task_id, assets, caption, brand, mode, executed_by)` -> data/published/<task>/caption.json + asset copies
- `actions.ats_update(task_id, shortlist, stage, executed_by, note)` -> data/hr/pipeline.json
- `actions.create_task(for_dept, title, detail=None, parent_id=None, created_by="auto", mode="live", gate="internal")`
  -> appends to data/tasks.jsonl a record {task_id, dept, title, detail, parent_id, created_by, gate, status:"queued", ts}
  and emits a `queued` event for that dept with output.kind="task" (server fans that out to the dept's webhooks).
  W3: GET /api/tasks?dept= should read data/tasks.jsonl in this format.
- `actions.done(dept, task_id, summary, mode, action, extra=None, parent_id=None)` -> `done` event with output.action.

## Files / dashboard (for W2)
- GET /dashboard serves static/dashboard.html (placeholder if missing).
- GET /files/outbox/<file>, /files/published/<task>/<file>, /files/design-out/<task>/<file> (path-safe; `..` -> 400).
  Every action dict has `url` (and design_publish has `files: [urls]`), so the feed can link directly.
- GET /api/automation/rules -> {"rules":[...]}.
- Done events with an executed action: `output.action = {type: email_outbox|design_publish|ats_update|task_created, path, url, executed_by: auto|founder}`.
- Actors you'll see: auto, founder, dev4-hr, dev4-design, dev4-qa-gate, grok-routine, dev1..dev4 bots.

## W3 notes (6:44 PM CT)
- lib/inbound.py: POST /api/inbound/{dept} (hr -> hire_needed trigger, design -> design_request trigger, emitted on dept
  `from_dept` or pseudo-dept `inbound` so flows' "dept != hr/design" match fires; other depts -> task), POST/GET /api/tasks
  (GET reads tasks.jsonl in actions.create_task format, status overlaid from the event log). MCP: tasks.create, tasks.list, inbound.post.
- lib/sched.py: thread every OPS_SCAN_SEC=60 (silent unless new anomaly), POST/GET /api/ops/scan, MCP ops.scan(actor). Dedupe file data/ops_anomalies.json (reset.sh should clear it; W3 adds that).
- lib/chains.py: adds chain.needs_qa->qa and chain.ops_task->dept (ops tasks with detail.auto_run re-run hr/design).
- W3 restarted the service at ~6:44 PM CT with ./stop.sh && ./start.sh to load these. Tell me here if you need it left alone.
- W3 -> W1 REQUEST: please add "demo" to the module loop in server.py: `for _m in ("inbound", "sched", "chains", "demo")`.
  lib/demo.py registers POST /api/demo/seed {pace_sec?} (async, returns run_id) + GET /api/demo/status. W2: Run demo button -> POST /api/demo/seed.
- W3 extended reset.sh: also archives tasks.jsonl, ops_anomalies.json, auto_seen.json, data/outbox, data/published (into data/archive/<stamp>/).

## Updates 6:50 PM CT
- GET /api/ops/kpis (and MCP ops.kpis): pending_founder_approvals now uses the same `_pending()` as GET /api/approvals (counts match).
- QA verdict events now inherit the task's mode (pass `mode` in the qa.check body, else the latest non-QA event of that task, else live).
- GET /api/stream: SSE. `event: event` + `data: <event JSON>` for each appended event, `: ping` every 15s, `retry: 2000`.
  W2: `new EventSource('/api/stream')`, on error fall back to 2s polling (server side done, dashboard not wired yet).
- MCP tools added: approvals.decide(task_id, decision, note), automation.rules().
- ATS (data/hr/pipeline.json) candidates are keyed "<task_id>:<candidate_id>".

## X03 design loop (W2, 6:50 PM CT)
- New `lib/design_loop.py`; `lib/depts.py` design_run got 2 small inserts (import + `design_loop.run(...)` after assets are made).
  Needs a service restart to load. Each design asset now has `brand_score`, `brand_reasons`, `brand_scorer`, `attempts` (+`first_score` on retry).
- Below 0.7 -> exactly one regenerate, logged as a `running` design event with `output.kind:"design_regenerate"`.
- Mock scorer is a rule check (palette/brand/size/MOCK label), labeled "MOCK rule check"; live uses Grok-MCP chat_with_vision (untested, no key).
- Test hook: `/api/design/run` body `force_low_score:true` makes the first logo off-brand. flows.py `_design` does not pass it through (W1's call).
- Dashboard: GET /api/stream is wired (SSE + 2 s polling fallback).

## Updates 6:55 PM CT (X01/X02/X07) for W3 smoke + W2 dashboard
- HR run output (hr needs_approval/done product event) may now include:
  - `jd {role, markdown, engine, mode}`: when the body has `role` or `write_jd:true`; always present for hire_needed chains.
  - `fairness {blind:true, removed:{names,emails,phones,schools,gendered_terms}, method}`: when `blind:true`. hire_needed chains default to blind; set output.blind:false to turn it off.
  - `interview_kit {engine, kits:[{candidate_id, questions:[{question,target_skill,type}], gaps}]}`: always present.
  - `role`. In blind runs, shortlist `initials` is "--".
- POST /api/hr/run also accepts `role`, `write_jd` and `blind`.
- Founder Approve on HR adds `output.onboarding {type:onboarding_plan, path, url:/files/onboarding/<file>, executed_by:founder}` to the done event.
- New files root: GET /files/onboarding/<file>.
- qa.check `check_results.openevals` = "skipped (no XAI_API_KEY)". It's a label only and is never scored.
- server.py module list is now ("inbound","sched","chains","demo","ops_ask","golden"). Each module exposes register(mcp); a missing one is skipped.
  W3: for X08, ship a python module with register(mcp) named lib/golden.py (already in the list); anything else, tell me the name.

## W3 X06 + X08 (6:58 PM CT)
- lib/ops_ask.py (already in W1's module loop as "ops_ask"): POST /api/ops/ask {question} (GET ?q=), GET /api/ops/metrics,
  MCP ops.ask / ops.metrics. Metrics live in data/metrics.yaml (11 governed metrics). MOCK keyword match unless XAI_API_KEY;
  SQL runs in a sandboxed DuckDB (snapshot table `events` only, external access off, SELECT only, 200 rows).
- lib/qa_golden.py: POST /api/qa/golden-check (same qa.check, log=False), GET /api/qa/reliability, POST /api/qa/reliability/run,
  MCP qa.reliability. Suite: qa/golden.yaml (promptfoo 0.124.1 via npx node@22). ops_ask.register() also registers qa_golden
  if server.py hasn't, so no server.py change is needed (optional: add "qa_golden" to the loop *before* "ops_ask"; it's guarded).
- Needs pyyaml in .venv (installed by W3 with uv pip).
- W2 dashboard request: (1) "QA reliability" tile from GET /api/qa/reliability -> show `passed/total`, `pass_rate`, `ran_at`
  (+ button POST /api/qa/reliability/run, then poll until running:false); (2) "Ask ops" box -> POST /api/ops/ask {question},
  show `answer`, `metric`, collapsible `sql`, and the `engine` label (MOCK badge when mode=mock).
- X08 found a real QA bug: BANNED_RE had `\b` before `\[insert...]`, so a placeholder after a space was never caught
  ("Thanks! [insert signature]" passed). W3 fixed the regex in lib/qa.py (one line, marked "X08 fix"). Old smoke only caught it via the card number.

## W2 dashboard (6:56 PM CT)
- Wired: SSE /api/stream (+2 s polling fallback), QA reliability tile (GET /api/qa/reliability, Re-run -> POST /api/qa/reliability/run),
  Ask ops box (POST /api/ops/ask), brand_score chips on design events/approvals, dept names 1-3 (orchestrator, research, marketing; aliases chief_of_staff, strategy, content).
  Tiles count from the last 400 events; feed shows newest 50. Slots 7-9 stay generic; any unknown dept that posts takes the next free one under its real name.

## Phase 2: Pulse Studio (trend-to-product brand), 7:20 PM CT

One trigger runs the whole chain (rules in `lib/pulse.py` + `lib/standins.py`, registered in the `lib/auto.py` engine):
`trend_spotted` -> Design `product_created` (MOCK SVG, brand score + retry once) -> QA product gate -> `listing_live` page
-> `POST /api/ops/order` -> `order_placed` + `margin_update`. All output is **MOCK**; payments are **Stripe test mode
labels only** (no Stripe call, no charge); print-on-demand is a MOCK provider writing `data/ops/orders.jsonl`.

| Endpoint | Body | Does |
|---|---|---|
| `POST /api/pulse/start` | `{trend?, why?, source? x\|backup\|manual, product_type?, price_usd?, cost_usd?, force_low_score?, backup_index?}` | Emits `trend_spotted` (dept research, actor `pulse`). No trend -> `data/trends/backup.json` (source backup) |
| `GET /api/pulse/trends` | | Backup trends |
| `GET /api/pulse/listings` | | live listings (newest first) + ops totals, for `/store` |
| `GET /store` | | storefront `static/store.html` (placeholder if missing) |
| `POST /api/ops/order` | `{task_id: <product task with listing_live>, qty 1..20}` | MOCK POD order + `order_placed` + `margin_update` (`computed_by: ops`); 404 if no listing |
| `POST /api/demo/seed` | `{"scenario":"pulse", ...same as pulse/start}` | Pulse demo trigger (old demo without scenario) |
| `GET /api/ops/kpis` | | now includes `pulse: {orders_count, revenue_usd, cost_usd, profit_usd, margin_pct, computed_by: ops}` |
| `POST /api/approvals/{task}` | `{decision: approved\|rejected\|approve\|reject, note}` | both spellings accepted |
| `POST /api/ops/ask` | `{question}` or `{q}` | new metrics: `orders_count`, `revenue_usd`, `margin_pct` |
MCP tools: `pulse.start`, `ops.order`.

QA product gate (`pulse.product_rules` + `qa.check` PII/banned rules): **fail** on trademark/IP names (Nike, Disney, Marvel,
Apple, ... see `TRADEMARKS`), offensive keywords, PII; **founder** on price outside $5-$60 or margin < 30%; founder approve
-> listing published (`executed_by: founder`), reject -> failed.

Event kinds (output.kind): `trend_spotted` {trend, why, source}, `product_brief`, `design_regenerate`, `product_created`
{product_type, title, tagline, price_usd, cost_usd, image, image_url, brand_score, attempts}, `product_blocked`, `listing_live`
{product, url, action.type=listing_publish}, `order_placed` {order_id, listing_task, qty, revenue_usd, cost_usd, payment.mode=test},
`margin_update` {computed_by ops|finance|finance-standin, margin_pct, totals}. Teammate kinds accepted as-is: `trend_accepted`,
`legal_precheck`, `posts_drafted`, `chain_stalled` (integrations). `listing_live` is also posted to sales/engineering/marketing webhooks.

Departments 7-9 (dev3): **finance**, **legal**, **integrations** (`lib/depts.py DEPARTMENTS`, dashboard v2 tiles).

**Stand-ins** (`lib/standins.py`, `STANDINS=1` default, `STANDIN_WAIT=8`, `STANDIN_STALL=30`): if a teammate's dept hasn't
emitted its step within the wait, dev4 does it, with `actor: standin-dev4`, `output.standin: true`, mode mock; any real event
from that dept referencing the trigger task cancels it. research `trend_accepted`; legal pre-check + `qa.check` -> `legal_precheck`;
engineering + sales `listing_live` (url); marketing 3 MOCK drafts `data/published/<task>/posts.md` (never posted); support one
canned buyer Q&A through QA (needs_qa); finance `margin_update` on `order_placed`; integrations `chain_stalled` if no
listing/blocked/founder step after 30s. Files: listing `/files/published/<task>/index.html`, art `/files/design-out-data/<file>`.
