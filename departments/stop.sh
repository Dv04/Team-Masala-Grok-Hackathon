#!/usr/bin/env bash
D="${DEPT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"; cd "$D"
for f in run/*.pid; do [ -e "$f" ] || continue; p=$(cat "$f"); n=$(basename "$f" .pid)
  if kill "$p" 2>/dev/null; then echo "STOP $n ($p)"; fi; pkill -P "$p" 2>/dev/null || true; rm -f "$f"; done
# uvx/npx children
pkill -f "mcp-server-motherduck --transport http --host 127.0.0.1 --port 8000" 2>/dev/null || true
pkill -f "openrecruiter-mcp --data-dir $D" 2>/dev/null || true
pkill -f "promptfoo mcp --transport http --port 3100" 2>/dev/null || true
