"""Data / ops (dept 12): fixed KPIs over the shared event log with DuckDB.
The same `events` view is what the DuckDB MCP server (port 8000) exposes."""
import os
import duckdb
import events

def view_sql(path=None):
    path = path or events.LOG
    return f"""CREATE OR REPLACE VIEW events AS
SELECT CAST(replace(ts,'Z','+00:00') AS TIMESTAMPTZ) AS ts, dept, task_id, parent_id, actor, status, summary,
       output, needs_approval, mode
FROM read_json('{path}', format='newline_delimited', ignore_errors=true,
  columns={{ts:'VARCHAR', dept:'VARCHAR', task_id:'VARCHAR', parent_id:'VARCHAR', actor:'VARCHAR',
           status:'VARCHAR', summary:'VARCHAR', output:'JSON', needs_approval:'BOOLEAN', mode:'VARCHAR'}});"""

Q = {
 "tasks_by_dept_status": """
  WITH latest AS (SELECT dept, task_id, arg_max(status, ts) AS status FROM events
                  WHERE dept NOT IN ('qa','founder') GROUP BY dept, task_id)
  SELECT dept, status, count(*) AS tasks FROM latest GROUP BY dept, status ORDER BY dept, status""",
 "pending_founder_approvals": """
  WITH latest AS (SELECT task_id, arg_max(dept, ts) AS dept, arg_max(status, ts) AS status,
                         arg_max(summary, ts) AS summary, max(ts) AS since FROM events
                  WHERE dept <> 'founder' GROUP BY task_id)
  SELECT task_id, dept, summary, strftime(since AT TIME ZONE 'UTC', '%Y-%m-%dT%H:%M:%SZ') AS since
  FROM latest WHERE status='needs_approval' ORDER BY since""",
 "avg_time_to_done_sec": """
  WITH t AS (SELECT dept, task_id, min(ts) AS t0, min(ts) FILTER (WHERE status='done') AS t1
             FROM events WHERE dept NOT IN ('qa','founder') GROUP BY dept, task_id)
  SELECT dept, count(*) AS done_tasks, round(avg(epoch(t1)-epoch(t0)),1) AS avg_sec
  FROM t WHERE t1 IS NOT NULL GROUP BY ROLLUP(dept) ORDER BY dept NULLS LAST""",
 "replies_while_founder_away": """
  WITH f AS (SELECT ts, CAST(json_extract(output,'$.away') AS BOOLEAN) AS away,
                    lead(ts) OVER (ORDER BY ts) AS until FROM events WHERE dept='founder'),
       w AS (SELECT ts AS t0, coalesce(until, TIMESTAMPTZ '9999-01-01') AS t1 FROM f WHERE away),
       r AS (SELECT ts FROM events WHERE status='done'
             AND json_extract_string(output,'$.kind') IN ('customer_reply','outbound_email'))
  SELECT count(*) AS replies FROM r WHERE EXISTS (SELECT 1 FROM w WHERE r.ts >= w.t0 AND r.ts < w.t1)""",
 "founder_away_now": """
  SELECT coalesce(arg_max(CAST(json_extract(output,'$.away') AS BOOLEAN), ts), false) FROM events WHERE dept='founder'""",
 "mode_counts": "SELECT mode, count(*) AS events FROM events GROUP BY mode ORDER BY mode",
}

def _rows(con, sql):
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

def kpis(path=None):
    path = path or events.LOG
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return {"tasks_by_dept_status": [], "pending_founder_approvals": {"count": 0, "items": []},
                "avg_time_to_done_sec": {"overall": None, "by_dept": []}, "replies_sent_while_founder_away": 0,
                "founder_away": False, "events_by_mode": [], "source": path}
    con = duckdb.connect()
    try:
        con.execute(view_sql(path))
        pend = _rows(con, Q["pending_founder_approvals"])
        ttd = _rows(con, Q["avg_time_to_done_sec"])
        overall = next((r for r in ttd if r["dept"] is None), None)
        return {
            "tasks_by_dept_status": _rows(con, Q["tasks_by_dept_status"]),
            "pending_founder_approvals": {"count": len(pend), "items": pend},
            "avg_time_to_done_sec": {"overall": overall["avg_sec"] if overall else None,
                                     "by_dept": [r for r in ttd if r["dept"] is not None]},
            "replies_sent_while_founder_away": con.execute(Q["replies_while_founder_away"]).fetchone()[0],
            "founder_away": bool(con.execute(Q["founder_away_now"]).fetchone()[0]),
            "events_by_mode": _rows(con, Q["mode_counts"]),
            "source": path,
        }
    finally:
        con.close()
