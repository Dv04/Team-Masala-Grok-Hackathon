#!/usr/bin/env bash
# Archive the event log + webhook registry + automation state/artifacts (e.g. after smoke tests) so the demo starts clean.
# Services can stay up. Nothing is deleted: everything moves to data/archive/<stamp>/.
D="${DEPT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"; cd "$D"; s=$(date +%Y%m%d-%H%M%S); A="data/archive/$s"; mkdir -p "$A"
[ -s data/events.jsonl ] && mv data/events.jsonl "$A/events.jsonl"; : > data/events.jsonl
[ -f data/webhooks.json ] && mv data/webhooks.json "$A/webhooks.json"; echo '[]' > data/webhooks.json
for f in tasks.jsonl ops_anomalies.json auto_seen.json; do [ -f "data/$f" ] && mv "data/$f" "$A/$f"; done
for d in outbox published hr/onboarding digests ops design-out; do [ -d "data/$d" ] && [ -n "$(ls -A data/$d 2>/dev/null)" ] && { mkdir -p "$A/$(dirname $d)"; mv "data/$d" "$A/$d"; }; mkdir -p "data/$d"; done
# kept on purpose: data/qa_reliability.json (last real golden-suite run, shown on the dashboard tile), data/fixtures, data/metrics.yaml
[ -f data/hr/pipeline.json ] && mv data/hr/pipeline.json "$A/pipeline.json"
echo "archived to $A"
