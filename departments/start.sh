#!/usr/bin/env bash
# Start dev4 departments (HR 10, Design 11, Data/ops 12, QA 13). Idempotent-ish: run stop.sh first if restarting.
# Ports: 8810 dept service (REST + MCP /mcp: qa.check etc.) | 8000 DuckDB MCP | 8792 open_recruiter MCP | 3100 promptfoo MCP (opt-in)
set -euo pipefail
D="${DEPT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"; cd "$D"; mkdir -p run logs data/hr design-out
touch data/events.jsonl; [ -f data/webhooks.json ] || echo '[]' > data/webhooks.json
.venv/bin/python -c "import sys;sys.path.insert(0,'lib');import ops;open('data/init.sql','w').write(ops.view_sql())"

port_busy(){ ss -ltn "( sport = :$1 )" | grep -q LISTEN; }
start(){ # name port cmd...
  local name=$1 port=$2; shift 2
  if port_busy "$port"; then echo "SKIP $name: port $port already in use"; return; fi
  setsid nohup "$@" > "logs/$name.log" 2>&1 & echo $! > "run/$name.pid"; echo "START $name pid $(cat run/$name.pid) port $port"
}

# 12 Data/ops: DuckDB MCP over the event log (view `events`)
start duckdb 8000 uvx mcp-server-motherduck --transport http --host 127.0.0.1 --port 8000 --db-path :memory: --read-write --init-sql "$D/data/init.sql"
# 10 HR: open_recruiter MCP (tools work only with XAI_API_KEY; list_jobs works without)
LLM_PROVIDER=xai LLM_MODEL="${HR_LLM_MODEL:-xai/grok-4}" start open_recruiter 8792 uvx openrecruiter-mcp --data-dir "$D/data/hr" --write --http --host 127.0.0.1 --port 8792

# 13 QA (optional): promptfoo MCP; our gate does rules itself + direct xAI rubric, so this is opt-in
if [ "${WITH_PROMPTFOO:-0}" = 1 ]; then start promptfoo 3100 npx -y -p node@22 -p promptfoo@latest -- promptfoo mcp --transport http --port 3100; fi
# dept service: QA gate + ops KPIs + HR/Design adapters + events/approvals/webhooks
start dept-service 8810 .venv/bin/python server.py

for i in $(seq 1 40); do curl -sf localhost:8810/health >/dev/null && port_busy 8000 && break; sleep 1; done
curl -s localhost:8810/health; echo
