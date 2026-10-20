"""dev3 Grok helper: live xAI Responses API calls for legal + finance, with an honest mock fallback.

Stdlib only. Calls https://api.x.ai/v1/responses only when XAI_API_KEY is set; otherwise returns a
deterministic fallback labeled mode "mock". Never raises into the caller and never logs or returns the key.

  legal_opinion(review_or_event) -> {"mode", "verdict": pass|flag, "opinion", "engine"}
  margin_summary(margin_output)  -> {"mode", "summary", "engine"}
"""
import json, os, sys, urllib.request

XAI_URL = os.environ.get("XAI_URL", "https://api.x.ai/v1/responses")
XAI_MODEL = os.environ.get("XAI_MODEL", "grok-4.3")
XAI_TIMEOUT = float(os.environ.get("XAI_TIMEOUT", "20"))


def _key():
    return (os.environ.get("XAI_API_KEY") or "").strip()


def _text(resp):
    """Pull the assistant text out of a Responses API body (output_text or output[].content[].text)."""
    if isinstance(resp.get("output_text"), str) and resp["output_text"].strip():
        return resp["output_text"].strip()
    parts = []
    for item in resp.get("output") or []:
        if isinstance(item, dict) and item.get("type") == "message":
            for c in item.get("content") or []:
                if isinstance(c, dict) and isinstance(c.get("text"), str):
                    parts.append(c["text"])
    return "\n".join(parts).strip()


def ask(system, user, max_chars=600):
    """Return (text, engine) from Grok, or (None, reason) if no key / any failure. Never raises."""
    key = _key()
    if not key:
        return None, "no XAI_API_KEY"
    body = {"model": XAI_MODEL, "reasoning": {"effort": "low"}, "store": False,
            "input": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(XAI_URL, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=XAI_TIMEOUT) as r:
            txt = _text(json.loads(r.read() or b"{}"))
        if not txt:
            return None, "empty Grok response"
        return txt[:max_chars], f"xai responses {XAI_MODEL}"
    except Exception as e:  # never surface the key: report the exception type only
        print(f"grok.ask failed: {type(e).__name__}", file=sys.stderr, flush=True)
        return None, f"Grok call failed ({type(e).__name__})"


LEGAL_SYS = ("You are the legal pre-check for Pulse Studio, a print-on-demand merch shop that turns X trends into "
             "stickers, tees and posters. Judge trademark/IP, right of publicity and Stripe/POD content rules. "
             "Answer on ONE line starting with PASS or FLAG, then a short reason (max 30 words).")


def legal_opinion(item):
    """item: a legal_review output or a trend_spotted/product_created event. Returns a second opinion dict."""
    item = item or {}
    o = item.get("output") if isinstance(item.get("output"), dict) else item
    subject = " | ".join(str(x) for x in (item.get("summary"), o.get("trend"), o.get("title"), o.get("name"),
                                          o.get("product"), o.get("slogan"), o.get("text")) if x and not isinstance(x, dict))
    rules = o.get("issues") or []
    txt, engine = ask(LEGAL_SYS, f"Item: {subject or '(empty)'}\nRule pre-check issues: {rules or 'none'}")
    if txt:
        verdict = "flag" if txt.upper().lstrip().startswith("FLAG") else "pass"
        return {"mode": "live", "verdict": verdict, "opinion": txt, "engine": engine}
    verdict = "flag" if rules else "pass"
    op = ("MOCK: agrees with rule pre-check, flagged: " + "; ".join(rules)) if rules else "MOCK: no rule issues found"
    return {"mode": "mock", "verdict": verdict, "opinion": op[:300], "engine": f"mock fallback ({engine})"}


FIN_SYS = ("You are the finance bot for Pulse Studio. Write ONE plain sentence (max 25 words) a founder can read "
           "at a glance about this order's margin. No markdown.")


def margin_summary(m):
    """m: finance margin_update output. Returns {"mode","summary","engine"}."""
    m = m or {}
    if not m.get("ok", True):
        return {"mode": "mock", "summary": f"No margin: missing {m.get('missing')}", "engine": "rules (no Grok call)"}
    facts = {k: m.get(k) for k in ("revenue", "cogs", "payment_fees", "margin", "margin_pct", "floor_pct", "under_floor")}
    txt, engine = ask(FIN_SYS, json.dumps(facts))
    if txt:
        return {"mode": "live", "summary": txt.splitlines()[0][:200], "engine": engine}
    pct = m.get("margin_pct") or 0
    s = f"MOCK: margin ${m.get('margin')} ({pct:.0%}) on ${m.get('revenue')}" + (" - under floor, founder to review price" if m.get("under_floor") else "")
    return {"mode": "mock", "summary": s, "engine": f"mock fallback ({engine})"}
