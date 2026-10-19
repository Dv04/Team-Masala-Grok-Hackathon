"""QA / approval gate (dept 13). Contract section 2.
Deterministic rule checks always run (no key). LLM rubric + factuality run only
when XAI_API_KEY is set (direct xAI chat completions); otherwise marked skipped.
"""
import json, os, re
import httpx
import events

FOUNDER_KINDS = {"refund", "payment", "discount", "legal", "pricing"}
SCORE_FLOOR = 0.7
XAI_URL = "https://api.x.ai/v1/chat/completions"
QA_MODEL = os.environ.get("QA_MODEL", "grok-4")

# hard-fail patterns: never send these to a customer
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+?\d{1,2}[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}\b")
BANNED_RE = re.compile(r"(\b(?:as an ai language model|password\s*[:=]|lorem ipsum|TODO|FIXME)|\[insert[^\]]*\])", re.I)  # X08 fix: \b before "[" never matched after a space
# soft policy words: route to founder (legal / pricing / money promises)
LEGAL_RE = re.compile(r"\b(lawsuit|legal action|liabilit\w*|contract|terms of service|guarantee[ds]?|warrant\w*|compensat\w*|sue)\b", re.I)
PRICING_RE = re.compile(r"(\b(refund\w*|discount\w*|coupon|price change|new price|free of charge|waive\w*)\b|\d+\s?% off|\$\s?\d)", re.I)
HYPE_RE = re.compile(r"\b(100% guaranteed|best in the world|risk[- ]free|act now)\b", re.I)


def _luhn(num):
    d = [int(c) for c in num if c.isdigit()]
    if not 13 <= len(d) <= 19: return False
    s = 0
    for i, x in enumerate(reversed(d)):
        if i % 2: x = x * 2 - 9 if x * 2 > 9 else x * 2
        s += x
    return s % 10 == 0


def _as_text(content):
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


def _rules(kind, content):
    text = _as_text(content)
    hard, soft, founder, results = [], [], [], {}
    # non-empty
    ok = bool(text.strip()) and text.strip() not in ("{}", "[]", '""', "null")
    results["nonempty"] = "pass" if ok else "fail"
    if not ok: hard.append("nonempty: content is empty")
    # JSON validity (only when content is meant to be JSON)
    if isinstance(content, (dict, list)):
        results["json"] = "pass"
    elif text.lstrip()[:1] in ("{", "["):
        try: json.loads(text); results["json"] = "pass"
        except json.JSONDecodeError as e:
            results["json"] = "fail"; hard.append(f"json: content looks like JSON but is invalid ({e.msg})")
    else:
        results["json"] = "n/a"
    # PII
    pii = []
    if SSN_RE.search(text): pii.append("SSN-like number")
    if any(_luhn(m.group()) for m in CARD_RE.finditer(text)): pii.append("payment card number")
    if events.SECRET_RE.search(text): pii.append("API key/secret")
    if pii:
        hard.append("pii: contains " + ", ".join(pii))
    contact = []
    if EMAIL_RE.search(text): contact.append("email address")
    if PHONE_RE.search(text): contact.append("phone number")
    if contact and kind == "public_post":
        hard.append("pii: public post contains " + ", ".join(contact))
    elif contact:
        soft.append("pii: contains " + ", ".join(contact) + " (ok for 1:1 replies, double-check recipient)")
    results["pii"] = "fail" if (pii or (contact and kind == "public_post")) else ("warn" if contact else "pass")
    # policy
    pol = "pass"
    m = BANNED_RE.search(text)
    if m: hard.append(f"policy: banned/placeholder text '{m.group()}'"); pol = "fail"
    m = LEGAL_RE.search(text)
    if m: founder.append(f"policy: legal wording '{m.group()}' needs founder"); pol = "founder" if pol == "pass" else pol
    m = PRICING_RE.search(text)
    if m and kind not in ("internal",):
        founder.append(f"policy: pricing/money wording '{m.group()}' needs founder"); pol = "founder" if pol == "pass" else pol
    m = HYPE_RE.search(text)
    if m: soft.append(f"policy: overclaim '{m.group()}'"); pol = "warn" if pol == "pass" else pol
    results["policy"] = pol
    return hard, soft, founder, results


def _llm(kind, content, context, key):
    """One xAI call returning rubric score (+ factuality when context given)."""
    sys_p = ("You are a strict QA reviewer for a small company's outgoing messages. "
             "Return ONLY JSON: {\"rubric_score\": 0..1, \"factuality_score\": 0..1 or null, \"reasons\": [short strings]}. "
             "Rubric: correct, helpful, polite, on-brief, no invented commitments. "
             "Factuality: only judge against the provided context; null if no context.")
    user_p = f"KIND: {kind}\nCONTEXT:\n{context or '(none)'}\n\nCONTENT TO SEND:\n{_as_text(content)}"
    r = httpx.post(XAI_URL, headers={"Authorization": f"Bearer {key}"}, timeout=45, json={
        "model": QA_MODEL, "temperature": 0, "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": sys_p}, {"role": "user", "content": user_p}]})
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])


def _prior_fails(task_id):
    return sum(1 for e in events.read_all()
               if e.get("task_id") == task_id and e.get("dept") == "qa"
               and (e.get("output") or {}).get("verdict") == "fail")


def check(req, log=True):
    for k in ("dept", "task_id", "kind"):
        if not req.get(k): raise ValueError(f"missing required field: {k}")
    if "content" not in req: raise ValueError("missing required field: content")
    dept, task_id, kind = req["dept"].lower(), req["task_id"], req["kind"].lower()
    content, context = req["content"], req.get("context") or ""
    hard, soft, founder, results = _rules(kind, content)

    if kind in FOUNDER_KINDS:
        founder.append(f"rule: kind '{kind}' always needs founder approval")
    first_contact = req.get("first_contact")
    if kind == "outbound_email" and first_contact is not False:
        founder.append("rule: first message to a new lead needs founder approval (send first_contact:false for follow-ups)")

    score = max(0.0, 1.0 - 0.15 * len(soft) - (0.5 if hard else 0.0))
    key = os.environ.get("XAI_API_KEY")
    mode = "rules_only"
    llm_note = None
    if key and not hard:
        try:
            j = _llm(kind, content, context, key)
            parts = [float(j.get("rubric_score", 0))]
            results["rubric"] = round(parts[0], 2)
            if j.get("factuality_score") is not None:
                parts.append(float(j["factuality_score"])); results["factuality"] = round(parts[-1], 2)
            else:
                results["factuality"] = "skipped (no context)"
            score = min(score, sum(parts) / len(parts))
            soft += [f"llm: {x}" for x in (j.get("reasons") or [])][:4]
            mode = "rules+llm"
        except Exception as e:
            results["rubric"] = results["factuality"] = "error"
            llm_note = f"llm: xAI rubric call failed ({type(e).__name__}); rules-only verdict"
            mode = "rules_only_llm_error"
    else:
        why = "skipped (no XAI_API_KEY)" if not key else "skipped (hard rule failed)"
        results["rubric"] = results["factuality"] = why

    # X07 (openevals hallucination judge, MIT): only a status label until the xAI key arrives; never scored
    results["openevals"] = "skipped (no XAI_API_KEY)" if not key else "skipped (openevals judge not wired yet)"
    if hard:
        verdict = "fail"
        if _prior_fails(task_id) >= 1:
            verdict = "founder"; founder.append("rule: second QA fail on same task escalates to founder")
    elif founder or score < SCORE_FLOOR:
        verdict = "founder"
        if score < SCORE_FLOOR: founder.append(f"rule: score {score:.2f} < {SCORE_FLOOR}")
    else:
        verdict = "pass"
    reasons = hard + founder + soft + ([llm_note] if llm_note else [])
    if not reasons: reasons = ["all checks passed"]
    resp = {"verdict": verdict, "score": round(score, 2), "reasons": reasons,
            "checks": ["nonempty", "json", "pii", "policy", "rubric", "factuality"],
            # extras beyond the contract (safe to ignore):
            "mode": mode, "check_results": results}
    if log:
        ev_mode = req.get("mode") if req.get("mode") in ("live", "mock") else next(
            (e.get("mode") for e in reversed(events.read_all()) if e.get("task_id") == task_id and e.get("dept") != "qa"), None) or "live"
        status = {"pass": "approved", "fail": "rejected", "founder": "needs_approval"}[verdict]
        events.emit("qa", task_id, status, f"QA {verdict} for {dept} {kind} (score {resp['score']})",
                    ev_mode, {"verdict": verdict, "score": resp["score"], "for_dept": dept, "kind": kind,
                              "qa_mode": mode, "reasons": reasons[:6], "check_results": results},
                    parent_id=req.get("parent_id"), actor="dev4-qa-gate",
                    needs_approval=(verdict == "founder"))
    return resp
