# 3-minute demo script: Team Masala / Pulse Studio
Judging criteria: Works 30 · Real work 25 · Grok Bot use 20 · Clarity 15 · Uniqueness 10. All times CT.

**Pre-flight (8:15 PM):**
1. `cd /workspace/departments && ./reset.sh` to clear test events.
2. Check `curl -s 127.0.0.1:8810/health` returns ok. If it doesn't, run `./start.sh`.
3. Open `http://127.0.0.1:8810/dashboard` full screen.
4. Have a live X trend ready (from research/Grok), plus the backup in `data/trends/backup.json`.
5. Have PR #2 open in a second tab.

| Time | What to show / do | What to say | Criterion |
|---|---|---|---|
| 0:00–0:20 | Dashboard: 13 tiles, company graph, MOCK and SANDBOX banners | "One founder, 13 departments run by AI agents, one live dashboard. The agents act. The founder approves only what's risky." | Clarity |
| 0:20–0:50 | Start Pulse: `POST /api/pulse/start` with the live trend (no trend = backup). Watch trend → Design → QA → listing pulses travel across the graph | "This trend is from X right now. Design turns it into a tee, brand-scores it and retries if it's off-brand. QA checks trademarks and PII." | Works, Uniqueness |
| 0:50–1:10 | Open the listing at `/files/published/<task>/index.html` | "This product didn't exist 60 seconds ago. Now it has a listing page with a test-mode Buy button." | Real work, Wow |
| 1:10–1:30 | `POST /api/ops/order {task_id}`: `order_placed` and `margin_update` appear and the KPIs update | "Ops takes a print-on-demand order (MOCK provider, Stripe test mode) and margin is computed from the same event log." | Real work |
| 1:30–1:50 | Trademark trend (e.g. a brand name), which becomes `product_blocked` | "The gate is real: a trademarked trend never ships." | Works, safety |
| 1:50–2:20 | Run demo: an engineering `hire_needed` goes through HR's blind shortlist and QA to the approval queue. Click **Approve** and show the outbox `.eml` and the onboarding plan | "First contact always goes to me. One click and the email (sandbox), ATS update and onboarding plan happen automatically." | Real work, Works |
| 2:20–2:40 | PR #2: TOON bot messages, the Ops routine digest, reviews from dev1, dev2 and dev3 | "Each of us has a Grok Bot. They negotiated the contract, reviewed each other's PR and found a real bug, all on this PR. Routines scan ops every 15 minutes." | Grok Bot use |
| 2:40–3:00 | QA reliability tile (16/16), Ask ops "how many approvals pending?" | "Reliability is tested: 66 of 66 smoke checks, a 16-case promptfoo suite. Anything still mocked is labeled MOCK until our xAI key goes in." | Works, honesty |

**Backup lines:**
- If X is quiet: "We keep a safe backup trend, so the demo never depends on the feed."
- If a call is slow: click **Run demo** on the dashboard, which seeds the HR and Design chains.

**Never claim:** live AI images, live Grok scoring or live email sends. Those are MOCK or sandbox tonight unless the key is set and tested.
