"""X06 (W3): governed metrics + natural-language questions for Data/ops (dept 12).
Concept: WrenAI-style semantic layer (Canner/WrenAI, Apache-2.0); idea reimplemented, no code copied.
  data/metrics.yaml   named metrics, each = description + keywords + SQL over the DuckDB `events` view
  ops.ask(question)   MOCK (no XAI_API_KEY): keyword overlap picks a metric (engine label says so)
                      LIVE (XAI_API_KEY set): Grok picks a metric or writes ONE SELECT over table `events`; untested until key arrives
  Safety: SQL runs in a fresh in-memory DuckDB holding only a snapshot table `events`, with external access disabled and
  config locked, single SELECT/WITH statement, 200-row cap. Answers always cite metric + SQL + engine.
REST: POST /api/ops/ask {question} (GET ?q=), GET /api/ops/metrics.  MCP: ops.ask, ops.metrics.
Also registers X08's QA reliability module (lib/qa_golden.py) if server.py doesn't load it itself."""
import json, os, re
import duckdb, httpx, yaml
from starlette.requests import Request
from starlette.responses import JSONResponse
import events, ops

ROOT = os.environ.get("DEPT_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METRICS_FILE = f"{ROOT}/data/metrics.yaml"
XAI_URL = "https://api.x.ai/v1/chat/completions"
MODEL = os.environ.get("OPS_ASK_MODEL", "grok-4")
MAX_ROWS = 200
STOP = {"the", "a", "an", "is", "are", "how", "many", "what", "which", "of", "in", "for", "to", "do", "we", "have", "by", "and", "me", "show", "any", "there"}
FORBIDDEN = re.compile(r"\b(read_\w+|glob|copy|attach|detach|install|load|pragma|set|reset|export|import|create|insert|update|delete|drop|alter|call|checkpoint)\b|;", re.I)

def metrics():
    return (yaml.safe_load(open(METRICS_FILE)) or {}).get("metrics", {})

def _words(s): return [w for w in re.findall(r"[a-z]+", s.lower()) if w not in STOP]

def pick_mock(question, ms):
    q = set(_words(question)); best, score = None, 0
    for name, m in ms.items():
        kw = set(m.get("keywords", [])) | set(name.split("_"))
        s = len(q & kw) + 0.1 * len(q & set(_words(m.get("description", ""))))
        if s > score: best, score = name, s
    return best, round(score, 2)

def run_sql(sql, path=None):
    """Run ONE read-only SELECT against a snapshot table `events` in a sandboxed DuckDB."""
    s = sql.strip().rstrip(";").strip()
    if not re.match(r"^(select|with)\b", s, re.I): raise ValueError("only a single SELECT/WITH query is allowed")
    if FORBIDDEN.search(s): raise ValueError("query uses a forbidden keyword/function (only plain SELECT over `events`)")
    path = path or events.LOG
    con = duckdb.connect()
    try:
        con.execute(ops.view_sql(path).replace("CREATE OR REPLACE VIEW events", "CREATE OR REPLACE VIEW events_src"))
        con.execute("CREATE TABLE events AS SELECT *, row_number() OVER () AS seq FROM events_src"); con.execute("DROP VIEW events_src")  # seq = append order (ts ties at ms)
        con.execute("SET enable_external_access = false"); con.execute("SET lock_configuration = true")
        cur = con.execute(f"SELECT * FROM ({s}) LIMIT {MAX_ROWS}")
        cols = [d[0] for d in cur.description]
        return cols, [dict(zip(cols, [v if isinstance(v, (int, float, str, bool, type(None))) else str(v) for v in r])) for r in cur.fetchall()]
    finally: con.close()

def _live_plan(question, ms):
    key = os.environ["XAI_API_KEY"]
    catalog = "\n".join(f"- {n}: {m['description']}" for n, m in ms.items())
    sys_p = ("You answer questions about a company's event log. Prefer a governed metric. Reply JSON only: "
             '{"metric": "<name or null>", "sql": "<one DuckDB SELECT over table events, only if no metric fits>"}. '
             "Table events(ts TIMESTAMPTZ, dept, task_id, parent_id, actor, status, summary, output JSON, needs_approval BOOLEAN, mode, seq BIGINT = append order). "
             f"Metrics:\n{catalog}")
    r = httpx.post(XAI_URL, headers={"Authorization": f"Bearer {key}"}, timeout=40,
                   json={"model": MODEL, "messages": [{"role": "system", "content": sys_p}, {"role": "user", "content": question}],
                         "response_format": {"type": "json_object"}, "temperature": 0})
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])

def ask(question, actor="api"):
    question = (question or "").strip()[:500]
    if not question: raise ValueError("need a question, e.g. 'how many approvals are pending?'")
    ms = metrics(); live = bool(os.environ.get("XAI_API_KEY"))
    metric, sql, engine, conf, note = None, None, None, None, None
    if live:
        try:
            plan = _live_plan(question, ms)
            if plan.get("metric") in ms: metric = plan["metric"]
            elif plan.get("sql"): sql = plan["sql"]
            engine = f"LIVE: Grok ({MODEL}) picked {'metric' if metric else 'ad-hoc SQL over events'}"
        except Exception as e:
            note = f"live planner failed ({type(e).__name__}); fell back to MOCK keyword match"
    if not metric and not sql:
        metric, conf = pick_mock(question, ms)
        engine = "MOCK: keyword -> governed metric match (no LLM)"
        if not metric:
            return {"ok": False, "question": question, "engine": engine, "mode": "mock",
                    "error": "no governed metric matches; try one of: " + ", ".join(ms), "metrics": list(ms)}
    if metric: sql = ms[metric]["sql"]
    cols, rows = run_sql(sql)
    res = {"ok": True, "question": question, "metric": metric, "description": ms[metric]["description"] if metric else "ad-hoc SQL (LIVE only)",
           "sql": sql.strip(), "columns": cols, "rows": rows, "answer": _sentence(metric, rows),
           "engine": engine, "mode": "live" if engine.startswith("LIVE") else "mock", "confidence": conf, "asked_by": actor}
    if note: res["note"] = note
    return res

def _sentence(metric, rows):
    if not rows: return "no rows (nothing logged yet for this metric)"
    if len(rows) == 1 and len(rows[0]) <= 2: return ", ".join(f"{k} = {v}" for k, v in rows[0].items())
    return f"{len(rows)} rows" + (f"; top: {rows[0]}" if rows else "")

def register(mcp, lock=None):
    import asyncio
    @mcp.custom_route("/api/ops/ask", methods=["GET", "POST"])
    async def api_ask(req: Request):
        if req.method == "GET": q, actor = req.query_params.get("q", ""), req.query_params.get("actor", "api")
        else:
            try: b = await req.json()
            except Exception: b = {}
            q, actor = (b or {}).get("question") or (b or {}).get("q", ""), (b or {}).get("actor", "api")
        try: return JSONResponse(await asyncio.to_thread(ask, q, str(actor)[:60]))
        except ValueError as e: return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    @mcp.custom_route("/api/ops/metrics", methods=["GET"])
    async def api_metrics(req: Request):
        return JSONResponse({"metrics": [{"name": n, "description": m["description"], "sql": m["sql"].strip()} for n, m in metrics().items()],
                             "source": "data/metrics.yaml"})

    @mcp.tool(name="ops.ask")
    async def ops_ask(question: str) -> dict:
        """Ask a question about the company's activity, e.g. 'how many approvals are pending?', 'which dept fails most?'.
        Answers from a governed metric (data/metrics.yaml) and returns metric name, SQL that ran, rows, and engine
        (MOCK keyword match without XAI_API_KEY; Grok-planned when keyed). Read-only."""
        return await asyncio.to_thread(ask, question, "mcp")

    @mcp.tool(name="ops.metrics")
    async def ops_metrics() -> list:
        """List governed metrics (name, description, SQL over the events view) that ops.ask can answer."""
        return [{"name": n, "description": m["description"], "sql": m["sql"].strip()} for n, m in metrics().items()]
    names = ["/api/ops/ask", "/api/ops/metrics", "ops.ask", "ops.metrics"]
    try:
        import qa_golden
        if not getattr(qa_golden, "REGISTERED", False): names += qa_golden.register(mcp)
    except ImportError: pass
    return names
