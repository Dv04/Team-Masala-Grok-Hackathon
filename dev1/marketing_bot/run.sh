#!/usr/bin/env bash
# Marketing bot. Webhook: http://127.0.0.1:8899/pulse
# Registers itself with the departments service (DEPARTMENTS_URL, default :8810).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"
export DEPARTMENTS_URL="${DEPARTMENTS_URL:-http://127.0.0.1:8810}"
export MARKETING_PORT="${MARKETING_PORT:-8899}"
export MARKETING_WEBHOOK_URL="${MARKETING_WEBHOOK_URL:-http://127.0.0.1:8899/pulse}"
exec python3 -m marketing_bot
