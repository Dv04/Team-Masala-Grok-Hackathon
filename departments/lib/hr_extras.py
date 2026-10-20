"""HR combined features (X01, X02).
X01 JD writer + 30/60/90 onboarding: structure from zubair-trabzada/ai-recruiter-claude (MIT), SKILL.md files vendored
    unmodified in vendor/ai-recruiter-claude/skills/{recruit-job,recruit-onboard}. Mock = our template filled with that
    skill's section layout; live = the SKILL.md is sent as the system prompt to xAI (untested until the key arrives).
X02 Blind screening + interview kit: pattern from Ismail-2001/agent-recruiter (MIT): BiasMitigator.mask_pii (mask identity
    before scoring) and InterviewGenerator (verify matched skills, probe gaps). Reimplemented here, no code copied; mock question bank."""
import os, re
import httpx
import qa

ROOT = os.environ.get("DEPT_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = f"{ROOT}/vendor/ai-recruiter-claude/skills"
ONBOARD_DIR = f"{ROOT}/data/hr/onboarding"
XAI_URL, MODEL = "https://api.x.ai/v1/chat/completions", os.environ.get("HR_MODEL", "grok-4")
SCHOOL_RE = re.compile(r"\b(?:[A-Z][\w&.-]*\s){0,4}(?:University|College|Institute|Academy|School)(?:\s(?:of|for)\s(?:[A-Z][\w&.-]*\s?){1,4})?", re.M)
NAME_LINE_RE = re.compile(r"^\s*name\s*:.*$", re.I | re.M)
GENDER_RE = re.compile(r"\b(he|she|him|her|his|hers|mr|mrs|ms)\b\.?", re.I)

def _skill(name):
    p = f"{SKILLS}/{name}/SKILL.md"
    return open(p).read() if os.path.exists(p) else ""

def _xai(system, user, key):
    r = httpx.post(XAI_URL, headers={"Authorization": f"Bearer {key}"}, timeout=60, json={
        "model": MODEL, "temperature": 0.2, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
    r.raise_for_status(); return r.json()["choices"][0]["message"]["content"]

# ---------- X01: JD writer ----------
def write_jd(role, job_text, mode):
    role = (role or "Founding Support & Ops Lead").strip()[:80]
    key = os.environ.get("XAI_API_KEY")
    if mode == "live" and key:
        try:
            md = _xai(_skill("recruit-job"), f"Write the optimized JD for: {role}\n\nNotes / original JD:\n{job_text}", key)
            return {"role": role, "markdown": md[:6000], "engine": "ai-recruiter-claude recruit-job SKILL.md via xAI", "mode": "live"}
        except Exception as e:
            note = f"live JD failed ({type(e).__name__}); template used"
    else:
        note = None
    words = [w for w in re.findall(r"[a-z][a-z+#.]{3,}", (job_text or "").lower())][:40]
    must = sorted(set(w for w in words if w in {"support", "sql", "helpdesk", "refunds", "escalations", "writing", "automation",
                                                 "python", "customer", "metrics", "spreadsheets", "docs"}))[:5] or ["customer support", "clear writing"]
    md = f"""### {role}  (MOCK draft: template, no LLM)

Help a one-person company answer every customer, fast and kindly, while the founder builds.

**About the Role**
You own customer support and day-to-day ops alongside a team of bot departments; you are the human escalation point.

**What You'll Do**
- Resolve escalations the support bots route to you within one business day
- Keep the help center accurate as the product changes
- Turn recurring tickets into fixes, docs or automations

**What We're Looking For (Must-Have)**
""" + "\n".join(f"- {m}" for m in must) + """

**Nice-to-Have**
- SQL / dashboards for support metrics
- Experience working with automation tools or AI agents

**Compensation & Benefits**
- Base salary: [band set by founder before posting]

**Equal Opportunity**
We welcome applicants of every background and evaluate candidates on skills, not pedigree.

**How to Apply**
Reply with a short note and a link to work you're proud of.

---
*MOCK template structured after ai-recruiter-claude `recruit-job` (MIT). Founder/legal review before posting.*"""
    out = {"role": role, "markdown": md, "engine": "MOCK: template following ai-recruiter-claude recruit-job layout", "mode": "mock"}
    if note: out["note"] = note
    return out

# ---------- X01: 30/60/90 onboarding ----------
def onboarding_plan(task_id, role, candidate, mode):
    os.makedirs(ONBOARD_DIR, exist_ok=True)
    c = candidate or {}; who = (c.get("initials") if c.get("initials") not in (None, "", "--") else None) or c.get("candidate_id") or "new hire"
    role = role or "Founding Support & Ops Lead"
    tag = "MOCK" if mode == "mock" else "LIVE"
    md = f"""# Onboarding Plan: {who} ({role})  [{tag}]
Draft prepared automatically when the founder approved outreach for task `{task_id}`. Becomes active only if the hire is made.

## Day 1 Setup Checklist
| Category | Items |
|---|---|
| Accounts | Email, team chat, helpdesk, event-log dashboard (/dashboard) |
| Access | Approval queue (read), knowledge base (write), QA gate results |
| Documentation | 13-department map, who-owns-what, escalation rules |
| Welcome | Founder intro call, first-week agenda |

## Week 1 Ramp Plan
| Day | Focus | Deliverable |
|---|---|---|
| 1 | Orientation, tools | Accounts active |
| 2 | Product + customers | 1-pager: how the business works |
| 3 | Bot departments (support, sales, QA gate) | 1-pager: where bots hand off to humans |
| 4 | Ticket history | Top 3 recurring issues |
| 5 | First small contribution | One help-center fix shipped, 30/60/90 signed |

## 30-Day Milestones (Learning)
- Handles all founder-routed escalations without help
- Knows every QA rule that sends work to a human

## 60-Day Milestones (Owning)
- Owns the help center and support KPIs end to end
- Proposed one automation that removes a recurring escalation

## 90-Day Milestones (Contributing)
- Operates with light founder oversight; founder approval queue down measurably
- Clear at-bar / above-bar signal from the founder

## Evaluation Criteria
Time-to-resolution on escalations, QA pass rate of human replies, founder hours saved.

---
*{tag}: structure adapted from ai-recruiter-claude `recruit-onboard` SKILL.md (MIT).{" Template-filled, no LLM." if mode == "mock" else ""}*
"""
    path = f"{ONBOARD_DIR}/{task_id}{'.MOCK' if mode == 'mock' else ''}.md"
    open(path, "w").write(md)
    return {"type": "onboarding_plan", "path": path, "executed_by": None}

# ---------- X02: blind screening ----------
def blind(resumes):
    """Strip name lines, emails, phones, school names and gendered words before ranking (agent-recruiter mask_pii pattern)."""
    out, removed = [], {"names": 0, "emails": 0, "phones": 0, "schools": 0, "gendered_terms": 0}
    for i, r in enumerate(resumes):
        t = r
        n = len(NAME_LINE_RE.findall(t)); removed["names"] += n
        t = NAME_LINE_RE.sub(f"Candidate {i+1} [masked]", t)
        if not n:  # first line is usually the name
            lines = t.strip().splitlines()
            if lines and len(lines[0].split()) <= 4: lines[0] = f"Candidate {i+1} [masked]"; removed["names"] += 1; t = "\n".join(lines)
        removed["emails"] += len(qa.EMAIL_RE.findall(t)); t = qa.EMAIL_RE.sub("[email masked]", t)
        removed["phones"] += len(qa.PHONE_RE.findall(t)); t = qa.PHONE_RE.sub("[phone masked]", t)
        removed["schools"] += len(SCHOOL_RE.findall(t)); t = SCHOOL_RE.sub("[school masked]", t)
        removed["gendered_terms"] += len(GENDER_RE.findall(t)); t = GENDER_RE.sub("they", t)
        out.append(t)
    return out, {"blind": True, "removed": removed,
                 "method": "reimplemented mask_pii pattern from agent-recruiter (MIT): identity masked before ranking, re-attached only for outreach"}

# ---------- X02: interview kit ----------
BANK = {
    "support": "Walk me through the hardest escalation you resolved. What did you do in the first hour?",
    "refunds": "A customer demands a refund outside policy. How do you respond, and when do you pull in the founder?",
    "escalations": "How do you decide what to escalate versus resolve yourself?",
    "sql": "Write (or describe) a query for median first-response time per week from a tickets table.",
    "spreadsheets": "How would you build a weekly support metrics sheet the founder reads in 2 minutes?",
    "automated": "Which ticket type would you automate first, and how would you know the automation is safe?",
    "help": "How do you keep help-center articles accurate when the product ships weekly?",
    "customer": "Tell me about a time you turned an angry customer into a promoter.",
    "python": "When would you script a support fix instead of handling tickets by hand?",
}
GAP_Q = "The role needs '{t}', which we did not see in your background. How would you get productive in it within 30 days?"

def interview_kit(shortlist, jd_text, mode):
    jd_terms = {w for w in re.findall(r"[a-z][a-z+#.]{2,}", (jd_text or "").lower())}
    kits = []
    for c in shortlist:
        matched = c.get("matched_terms") or []
        qs = [{"question": BANK[t], "target_skill": t, "type": "verify_match"} for t in matched if t in BANK][:3]
        gaps = [t for t in ("sql", "escalations", "refunds", "help", "support") if t in jd_terms and t not in matched][:2]
        qs += [{"question": GAP_Q.format(t=t), "target_skill": t, "type": "probe_gap"} for t in gaps]
        if not qs: qs = [{"question": BANK["customer"], "target_skill": "customer", "type": "general"}]
        kits.append({"candidate_id": c.get("candidate_id"), "questions": qs, "gaps": gaps})
    return {"engine": "MOCK: fixed question bank (agent-recruiter InterviewGenerator pattern: verify matches, probe gaps)"
            if mode == "mock" else "question bank (live LLM kit not wired)", "kits": kits}
