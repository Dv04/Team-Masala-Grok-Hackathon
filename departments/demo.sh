#!/usr/bin/env bash
# T11: 90-second demo. reset -> POST /api/demo/seed (founder away, hire_needed, design_request, bad caption, needs_qa reply,
# ops anomaly, founder back) -> print what the engine did. Open http://127.0.0.1:8810/dashboard to watch.
set -euo pipefail
D="${DEPT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"; cd "$D"; A=${DEPT_API:-http://127.0.0.1:8810}; PACE=${PACE:-4}
[ "${NO_RESET:-0}" = 1 ] || ./reset.sh
curl -sf "$A/health" >/dev/null || { echo "dept service not up on $A (run ./start.sh)"; exit 1; }
rm -f /tmp/demo_steps.json; code=$(curl -s -o /tmp/demo_seed.json -w '%{http_code}' -X POST "$A/api/demo/seed" -H 'content-type: application/json' -d "{\"pace_sec\": $PACE}")
if [ "$code" = 200 ]; then cat /tmp/demo_seed.json; echo
  for i in $(seq 1 80); do sleep 1; curl -s "$A/api/demo/status" | grep -q '"running":false' && break; done
else echo "POST /api/demo/seed -> $code (demo module not wired into server.py yet); running the same steps over REST"
  .venv/bin/python lib/demo.py "$A" "$PACE" > /tmp/demo_steps.json; fi
sleep 3
.venv/bin/python - "$A" <<'PY'
import json, sys, urllib.request
A = sys.argv[1]; g = lambda p: json.load(urllib.request.urlopen(A + p))
import os
try: st = g("/api/demo/status")
except Exception: st = json.load(open("/tmp/demo_steps.json"))
if not st.get("steps") and os.path.exists("/tmp/demo_steps.json"): st = json.load(open("/tmp/demo_steps.json"))
for s in st["steps"]: print(("OK  " if s["ok"] else "ERR ") + s["step"], s.get("error", ""))
evs = g("/api/events?limit=400")["events"]
acts = [e for e in evs if e["status"] == "done" and isinstance((e.get("output") or {}).get("action"), dict)]
print(f"events: {len(evs)} | executed actions: {len(acts)}")
for e in acts: a = e["output"]["action"]; print(f"  {e['dept']:<8} {a.get('type'):<15} {a.get('url') or a.get('path')}  by {a.get('executed_by')}")
print("pending approvals:", [(p["dept"], p["task_id"]) for p in g("/api/approvals?pending=true")["pending"]])
print("support tasks:", [t["title"] for t in g("/api/tasks?dept=support")["tasks"]])
PY
