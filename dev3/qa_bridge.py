"""dev3 qa.check bridge: routes finance and legal results through dev4's QA gate (POST /api/qa/check).

Body matches departments/lib/qa.check exactly: {dept, task_id, kind, content, context?, mode?}.
Response: {verdict: pass|fail|founder, score, reasons, ...}. If the hub is down, returns
{"verdict": "unavailable", "error": ...} instead of raising.

  margin_check(task_id, margin_output)  kind "pricing" (always founder in dev4's gate) for margin under floor
  legal_check(task_id, legal_review)    kind "legal" for flags only (passes return None: no founder-queue flood)
"""
import json, os, urllib.request

HUB = (os.environ.get("HUB") or os.environ.get("HUB_URL") or "http://127.0.0.1:8810").rstrip("/")
TIMEOUT = float(os.environ.get("DEV3_QA_TIMEOUT", "8"))


def _post(path, body, hub=None):
    req = urllib.request.Request((hub or HUB).rstrip("/") + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read() or b"{}")


def qa_check(dept, task_id, kind, content, context="", mode="live", hub=None):
    body = {"dept": dept, "task_id": task_id, "kind": kind, "content": content, "mode": mode}
    if context:
        body["context"] = context
    try:
        res = _post("/api/qa/check", body, hub)
        if not isinstance(res, dict) or "verdict" not in res:
            return {"verdict": "unavailable", "error": f"unexpected response: {str(res)[:120]}"}
        return res
    except Exception as e:
        return {"verdict": "unavailable", "error": f"{type(e).__name__}: {e}"[:200]}


def margin_check(task_id, m, hub=None, mode="live"):
    """Only margins under the floor go to QA (kind pricing). Returns None when no check is needed."""
    if not m or not m.get("ok") or not m.get("under_floor"):
        return None
    content = (f"Pulse Studio order margin {m.get('margin_frac', 0):.1%} (${m.get('margin')}) is under the "
               f"{m.get('floor_pct', 25)}% floor: revenue ${m.get('revenue')}, cogs ${m.get('cogs')}, "
               f"fees ${m.get('payment_fees')}. Founder to approve or reprice.")
    return qa_check("finance", task_id, "pricing", content, context="dev3 finance margin_update", mode=mode, hub=hub)


def legal_check(task_id, review, hub=None, mode="live", opinion=None):
    """Only legal FLAGS go through QA (kind legal always routes to the founder in dev4's gate, so sending passes
    would flood the founder queue). Returns None for a pass."""
    review = review or {}
    verdict = review.get("verdict", "pass")
    if verdict != "flag":
        return None
    issues = review.get("issues") or []
    content = f"Legal pre-check {verdict.upper()} on {review.get('checked_kind') or 'item'} {review.get('checked') or task_id}: " + \
              ("; ".join(issues) if issues else "no protected marks, real people or restricted content found")
    ctx = "dev3 legal_review (rules pre-check)"
    if opinion:
        ctx += f"; Grok second opinion ({opinion.get('mode')}): {opinion.get('opinion', '')[:200]}"
    return qa_check("legal", task_id, "legal", content, context=ctx, mode=mode, hub=hub)
