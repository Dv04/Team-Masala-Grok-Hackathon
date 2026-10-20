# Team Masala - Grok Bot Austin Hackathon

Fresh start on Oct 19, 2026. Previous starter preserved on branch `pre-reset-backup`.

Team comms live on PR #2 (draft, do not merge).

Rules: never commit API keys or secrets; label mock output as mock.

## departments/

`departments/` is the working department service: event log, automation engine, QA approval gate, approvals, webhooks, Ops scheduler, and the HR, Design, Data, and QA departments. `GET /dashboard` is the one shared company dashboard every department plugs into.

Run it (port is `DEPT_PORT`, default `8810`):

```bash
python3 -m venv .venv
.venv/bin/pip install -r departments/requirements.txt
DEPT_PORT=8810 .venv/bin/python departments/server.py
```

`GET /health` and `GET /dashboard` should both return 200. A department posts work with `POST /api/events` (include its `dept` name) and can subscribe with `POST /api/webhooks`. `departments/start.sh` can also start optional external MCP servers (DuckDB, open_recruiter, promptfoo); those are not required to boot the service. Without `XAI_API_KEY`, HR and Design stay in mock mode and QA runs rules only. Do not commit `.env`, `.venv/`, or `data/*.jsonl` logs.
