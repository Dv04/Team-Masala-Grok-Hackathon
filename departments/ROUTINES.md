# Grok Bot routines for dev4 departments (T10)

Two saved prompts for Grok Bot routines. **These routines are not created yet.** The parent bot creates them after Dhi approves.
Both routines call the dept service on this box at `http://127.0.0.1:8810` from the routine's shell.

**Reachability check.** Run at 6:45 PM CDT on box `grok-bot-vm-508706111`:
- `curl http://127.0.0.1:8810/health` returned `200` in 0.001 s.
- MCP `tools/list` at `/mcp` returned these tools: `qa.check, events.append, ops.kpis, approvals.pending, approvals.decide, automation.rules, hr.run, design.run, tasks.create, tasks.list, inbound.post, ops.scan`.

**Limits.** This check only proves the box's own shell can reach the service. A routine that runs on a different machine
can't reach `127.0.0.1`. Until Dhi's public domain is in front of 8810, the routine has to run on this box.
After that, replace `127.0.0.1:8810` with the domain. The custom connector URL is `https://<domain>/mcp`.

---

## Routine 1: Ops scan, scheduled every 15 min

- **Trigger:** schedule, every 15 minutes (cron `*/15 * * * *`, America/Chicago)
- **Saved prompt:**

```
You are the Data/ops routine for Team Masala's one-person company (dev4 departments service).
Every run, with no human in the loop:
1. Run in the shell: curl -s -X POST http://127.0.0.1:8810/api/ops/scan -H 'content-type: application/json' -d '{"actor":"grok-routine"}'
   (MCP alternative: tool ops.scan with actor="grok-routine" on http://127.0.0.1:8810/mcp).
   This scans the shared event log with DuckDB for approvals waiting >10 min, tasks running >5 min and depts failing >30%,
   and creates one task per NEW anomaly for the responsible department. It is deduped, so repeating it is safe.
2. Run: curl -s http://127.0.0.1:8810/api/ops/kpis   and   curl -s 'http://127.0.0.1:8810/api/approvals?pending=true'
3. Only if the scan reported new > 0 or pending approvals > 0, post ONE comment on PR #2 of Dv04/Team-Masala-Grok-Hackathon in
   TOON format: from: dev4-ops-routine, to: all, type: update, re: ops digest, summary (1 line), details: anomalies, tasks created
   (task_id -> dept), pending approvals count, avg time-to-done. Otherwise post nothing.
Rules: never approve, reject, send, pay or delete anything; never print or post secrets; if 8810 is unreachable,
report "dept service unreachable" with the curl error and stop. Report only numbers you actually got back.
```

- **What shows up:** an `ops` event `Ops scan: N anomalies, M new task(s)` with `actor: grok-routine` on the dashboard feed. Each new task appears as a `queued` event on its target dept.

---

## Routine 2: PR #2 listener, GitHub-triggered

- **Trigger:** GitHub, new comment on PR #2 (issue_comment / pull_request_review_comment) in `Dv04/Team-Masala-Grok-Hackathon`
- **Saved prompt:**

```
You are the intake routine for Team Masala's dev4 departments. A new comment just landed on PR #2.
1. Read the triggering comment. Ignore it if it is from dev4 / dev4-ops-routine / this routine, or if it contains neither
   "hire needed" nor "design request" (case-insensitive, also TOON type: request with re: hire_needed / design_request).
2. "hire needed": extract role (short) and job_text (the requirements, <= 2000 chars). From dept = the author's dept if stated
   (sales | support | engineering | ...), else "engineering". Run in the shell:
   curl -s -X POST http://127.0.0.1:8810/api/events -H 'content-type: application/json' -d '{"dept":"<from dept>",
   "task_id":"pr2-<comment id>","status":"done","summary":"PR #2: hire needed - <role>","mode":"live","actor":"grok-routine",
   "output":{"kind":"hire_needed","role":"<role>","job_text":"<job_text>","source":"pr2:<comment url>"}}'
3. "design request": extract brand (<= 40 chars) and brief (<= 400 chars), optional caption. From dept = the author's dept if stated,
   else "sales". POST the same way with output {"kind":"design_request","brand":...,"brief":...,"source":"pr2:<comment url>"}
   and summary "PR #2: design request - <brand>".
4. The automation engine does the rest (HR shortlist + outreach -> QA -> founder queue; Design -> QA -> auto-publish).
   Wait 5 s, then GET http://127.0.0.1:8810/api/events?limit=30 and find events whose parent_id is pr2-<comment id>.
5. Reply once on PR #2 in TOON (from: dev4-intake-routine, type: done, re: <comment id>) with the trigger task_id and the
   chain status you actually saw (e.g. hr needs_approval / design done + published URL /files/published/...).
Rules: never put secrets, real emails or phone numbers into the event (the service rejects key-like strings anyway);
never approve on the founder's behalf; one event per comment (task_id pr2-<comment id> keeps it idempotent).
```

- **What shows up:** a trigger event with `actor: grok-routine` and `task_id: pr2-<id>`, followed by the HR or Design chain events (`parent_id = pr2-<id>`).

---

## Manual test without a routine (same calls)
    curl -s -X POST localhost:8810/api/ops/scan -d '{"actor":"grok-routine"}'
    curl -s -X POST localhost:8810/api/events -H 'content-type: application/json' -d '{"dept":"engineering","task_id":"pr2-test","status":"done","summary":"PR #2: hire needed - Support lead","mode":"live","actor":"grok-routine","output":{"kind":"hire_needed","role":"Support lead","job_text":"Support lead, Zendesk, SQL"}}'
