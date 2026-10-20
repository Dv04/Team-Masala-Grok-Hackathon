# Presentation outline (9 slides): Team Masala
Source of truth: `PROJECT.md`. Keep claims to what's listed there.

## 1. Team Masala: a one-person company run by 13 AI departments
- One founder, 13 agent-run departments, one live dashboard
- Phase 2 product: **Pulse Studio**, X trend → product for sale in minutes
- Built tonight at the Grok Bot Austin hackathon, Oct 19, 2026
> Notes: Open with the wow promise: "By the end of this, a product that doesn't exist yet will be for sale."

## 2. The problem
- A solo founder can't run sales, support, hiring, design, ops and QA at once
- Most agent demos stop at chat logs and take no real actions
- Unchecked agents are risky: money, legal, first contact
> Notes: Frame it as "agents that do real work, with a gate."

## 3. Pulse Studio
- Grok spots a rising X trend → Design makes a sticker, tee or poster
- Legal and QA gate it → listing goes live → Marketing posts
- Ops takes a print-on-demand order (test mode) → Finance tracks margin
- Backup trend is ready, so the demo never depends on the feed
> Notes: Name who owns each step (research dev1, design/qa/ops dev4, launch dev2, finance/legal dev3).

## 4. Architecture: one hub, 13 departments
- Shared service: event log, automation engine, QA gate, approvals, webhooks, scheduler
- One contract: `POST /api/events`, `qa.check`, webhooks, MCP at `/mcp`
- One company dashboard, live over SSE; no per-team dashboards
- DuckDB MCP for analytics, promptfoo for regression, xAI as the only model provider
> Notes: Show the mermaid diagram from PROJECT.md §6.

## 5. Events trigger real actions
- Engineering `hire_needed` → HR blind shortlist → QA → founder → outbox email, ATS update, onboarding plan
- Sales or Support `design_request` → Design brand score and retry → QA → auto-publish
- Any `needs_qa` → automatic verdict webhooked back; Ops anomalies → tasks
- Idempotent across restarts, 5-hop loop guard
> Notes: Emphasize "no human between trigger and action unless a rule says founder."

## 6. The founder gate (safety)
- QA rules: PII, card numbers and keys fail; refunds, pricing, legal and first contact go to the founder
- Pulse: trademarks are blocked; price outside $5–$60 or margin under 30% goes to the founder
- Sandbox outbox with fictional recipients, Stripe test mode, MOCK labels, no secrets in the repo
> Notes: Honesty is part of the pitch: we label mock output as mock.

## 7. Grok Bot did the work
- Four Grok Bots coordinated on PR #2 in TOON: contract, reviews, product decision (30 messages)
- Routines: Ops scan every 15 minutes posts digests; the PR #2 listener turns comments into tasks
- Cloud agents pushed the code and opened the PRs; parallel subagents built the departments
- Teammates' bots reviewed PR #5 and found a real bug, fixed before the merge
> Notes: This is 20 points. Show the PR #2 thread live.

## 8. Reliability and open-source remix
- Smoke 66/66 (box), 64/64 plus 2 skipped on a clean machine; promptfoo golden suite 16/16
- Combined: ai-recruiter-claude, agent-recruiter, open_recruiter, Grok-MCP, adk-recipes loop, DuckDB MCP, WrenAI-style metrics, promptfoo (MIT/Apache-2.0)
- The golden suite caught a real placeholder-regex bug
> Notes: Credit repos and licenses, and say what's reimplemented vs copied.

## 9. What's live, what's next
- Live: engine, gate, approvals, ops SQL, dashboard, routines
- MOCK until the xAI key: Grok images and vision, HR ranking, rubric scoring
- Next: xAI key live run, public URL, teammates' department PRs, real POD and Stripe test checkout
> Notes: Close on the wow: point at the product that's now for sale.
