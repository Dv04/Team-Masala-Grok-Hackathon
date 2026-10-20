#!/usr/bin/env bash
# Smoke the orchestrator against the department service.
# Uses departments/start.sh when port 8810 is down. If the optional MCP
# processes in start.sh cannot launch, boots departments/server.py directly.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
DEPT="$REPO/departments"
BASE="${DEPT_SERVICE_URL:-http://127.0.0.1:8810}"

health_ok() { curl -sf "$BASE/health" >/dev/null; }

if ! health_ok; then
  if [[ -x "$DEPT/start.sh" && -x "$DEPT/.venv/bin/python" ]]; then
    echo "starting departments/start.sh"
    (cd "$DEPT" && ./start.sh) || true
  fi
fi

if ! health_ok; then
  echo "start.sh did not leave 8810 healthy; starting departments/server.py"
  if [[ ! -x "$DEPT/.venv/bin/python" ]]; then
    python3 -m venv "$DEPT/.venv"
    "$DEPT/.venv/bin/pip" install -q -r "$DEPT/requirements.txt"
  fi
  (cd "$DEPT" && setsid nohup .venv/bin/python server.py > logs/dept-service.log 2>&1 & echo $! > run/orchestrator-smoke.pid)
  for _ in $(seq 1 30); do
    health_ok && break
    sleep 1
  done
fi

if ! health_ok; then
  echo "FAIL dept service never became healthy at $BASE"
  exit 2
fi

cd "$HERE"
python3 smoke.py
