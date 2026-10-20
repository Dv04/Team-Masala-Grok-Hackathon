#!/usr/bin/env bash
# Build /workspace/departments-dev4.tar.gz (top folder departments/) for branch dev4. Source only: no data logs, no venvs, no secrets.
# The staged copy gets the hardcoded /workspace/departments paths rewritten to "this folder" (DEPT_ROOT env or the file's own location),
# so the package runs from any checkout. The live tree is left untouched.
set -euo pipefail
SRC=/workspace/departments; OUT=${1:-/workspace/departments-dev4.tar.gz}
ST=$(mktemp -d /tmp/pack-stage.XXXX); D="$ST/departments"; mkdir -p "$D"
cd "$SRC"
tar cf - --exclude='__pycache__' --exclude='.venv' --exclude='node_modules' --exclude='.git' --exclude='*.pyc' \
  --exclude='.env' --exclude='*.duckdb' --exclude='*.db' \
  server.py lib static vendor qa bin smoke.py demo.sh start.sh stop.sh reset.sh pack.sh \
  README.md PLAN.md TASKS.toon ROUTINES.md INTERFACES.md data/fixtures data/metrics.yaml 2>/dev/null | tar xf - -C "$D"
for d in data/outbox data/published data/hr/onboarding data/archive logs run design-out; do mkdir -p "$D/$d"; touch "$D/$d/.gitkeep"; done
cat > "$D/requirements.txt" <<'EOF'
# dept service (server.py + lib/). Python 3.11+. External MCP servers are started by start.sh via uvx/npx.
mcp==1.26.0
httpx==0.28.1
duckdb==1.5.6
PyYAML==6.0.3
uvicorn==0.54.0
starlette==1.9.0
EOF
cat > "$D/.env.example" <<'EOF'
# Copy to .env (never commit .env). Every value here is a placeholder.
XAI_API_KEY=
DEPT_PORT=8810
DEPT_HOST=127.0.0.1
DEPT_ROOT=
QA_MODEL=grok-4
HR_MODEL=grok-4
HR_LLM_MODEL=xai/grok-4
WITH_PROMPTFOO=0
EOF
cat > "$D/.gitignore" <<'EOF'
.venv/
node_modules/
__pycache__/
*.pyc
.env
*.duckdb
*.db
data/*.jsonl
data/*.json
data/init.sql
data/archive/*
data/outbox/*
data/published/*
data/hr/*
!data/hr/onboarding/
data/hr/onboarding/*
logs/*
run/*
design-out/*
!**/.gitkeep
EOF
python3 - "$D" <<'EOF'
import pathlib, re, sys
D = pathlib.Path(sys.argv[1]); HERE = 'os.environ.get("DEPT_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))'
for f in (D / "lib").glob("*.py"):
    s = f.read_text(); t = s.replace('ROOT = "/workspace/departments"', f"ROOT = {HERE}")
    t = t.replace('"/workspace/departments/data/events.jsonl"', f'os.path.join({HERE}, "data", "events.jsonl")')
    if t != s: f.write_text(t)
SH = 'D="${DEPT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"'
for n in ("start.sh", "stop.sh", "reset.sh", "demo.sh", "pack.sh"):
    f = D / n; s = f.read_text()
    if n == "pack.sh": continue  # dev-box tool, documents its own SRC
    s = s.replace("D=/workspace/departments;", SH + ";", 1)
    if SH not in s: s = s.replace("cd /workspace/departments", SH + '; cd "$D"', 1)
    s = s.replace("/workspace/departments", "$D")
    f.write_text(s)
left = [str(p.relative_to(D)) for p in D.rglob("*") if p.is_file() and p.suffix in (".py", ".sh") and p.name != "pack.sh"
        and "vendor" not in p.parts and "/workspace/departments" in p.read_text(errors="ignore")]
print("hardcoded paths left:", left or "none")
EOF
tar czf "$OUT" -C "$ST" departments
echo "TARBALL $OUT $(du -h "$OUT" | cut -f1) files=$(tar tzf "$OUT" | grep -vc '/$')"
echo "STAGE $D"
