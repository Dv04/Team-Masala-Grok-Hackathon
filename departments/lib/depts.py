"""HR (dept 10) and Design (dept 11) adapters.
Live path only when XAI_API_KEY is set; otherwise clearly labeled mock output."""
# All 13 departments (tile number -> dept id, name, owner). dev3 confirmed 7 finance, 8 legal, 9 integrations (7:12 PM CT).
DEPARTMENTS = {1: ("orchestrator", "Orchestrator / Chief of Staff", "dev1"), 2: ("research", "Research & strategy", "dev1"),
               3: ("marketing", "Marketing & content", "dev1"), 4: ("sales", "Sales", "dev2"), 5: ("support", "Support", "dev2"),
               6: ("engineering", "Engineering", "dev2"), 7: ("finance", "Finance", "dev3"), 8: ("legal", "Legal", "dev3"),
               9: ("integrations", "Integrations", "dev3"), 10: ("hr", "HR", "dev4"), 11: ("design", "Design", "dev4"),
               12: ("ops", "Data / Ops", "dev4"), 13: ("qa", "QA / approval gate", "dev4")}
import asyncio, hashlib, json, os, re
from mcp import ClientSession, StdioServerParameters
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.stdio import stdio_client
import events, qa, design_loop

ROOT = os.environ.get("DEPT_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HR_MCP = os.environ.get("HR_MCP_URL", "http://127.0.0.1:8792/mcp")
GROK_MCP_DIR = os.environ.get("GROK_MCP_DIR", f"{ROOT}/vendor/Grok-MCP")
DESIGN_OUT = f"{ROOT}/design-out"
EMAIL_RE, PHONE_RE = qa.EMAIL_RE, qa.PHONE_RE

def live(): return bool(os.environ.get("XAI_API_KEY"))

def _scrub(s):
    s = EMAIL_RE.sub("[email redacted]", s)
    return PHONE_RE.sub("[phone redacted]", s)

def _tool_json(res):
    if getattr(res, "isError", False):
        raise RuntimeError("tool error: " + " ".join(getattr(c, "text", "") for c in res.content)[:300])
    sc = getattr(res, "structuredContent", None)
    if sc: return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    txt = "".join(getattr(c, "text", "") for c in res.content)
    try: return json.loads(txt)
    except Exception: return txt

def _gate(dept, task_id, kind, content, context, parent_id, mode, actor=None):
    """Route output through QA; one revise+recheck on fail. Returns (final_status, qa_resp)."""
    r = qa.check({"dept": dept, "task_id": task_id, "kind": kind, "content": content,
                  "context": context, "parent_id": parent_id})
    if r["verdict"] == "fail":
        events.emit(dept, task_id, "running", f"{dept}: revising after QA fail", mode,
                    {"qa_reasons": r["reasons"][:4]}, parent_id, actor or f"dev4-{dept}")
        content = _scrub(content) if isinstance(content, str) else content
        r = qa.check({"dept": dept, "task_id": task_id, "kind": kind, "content": content,
                      "context": context, "parent_id": parent_id})
    status = {"pass": "done", "founder": "needs_approval", "fail": "failed"}[r["verdict"]]
    return status, r, content

# ---------------- HR ----------------
DEFAULT_JD = open(f"{ROOT}/data/fixtures/jd.txt").read() if os.path.exists(f"{ROOT}/data/fixtures/jd.txt") else ""
def _fixture_resumes():
    d = f"{ROOT}/data/fixtures/resumes"
    return [open(os.path.join(d, f)).read() for f in sorted(os.listdir(d))] if os.path.isdir(d) else []

WORD = re.compile(r"[a-z][a-z+#.]{2,}")
STOP = set("the and for with you our are will this that from have has job role team who your work into able years year experience".split())

def _mock_rank(jd, resumes):
    jw = {w for w in WORD.findall(jd.lower()) if w not in STOP}
    out = []
    for i, r in enumerate(resumes):
        first = r.strip().splitlines()[0] if r.strip() else f"Candidate {i+1}"
        name = re.sub(r"^(name\s*:\s*)", "", first, flags=re.I).strip()
        rw = {w for w in WORD.findall(r.lower()) if w not in STOP}
        hit = sorted(jw & rw)
        out.append({"candidate_id": f"mock-c{i+1}", "initials": "".join(p[0] for p in name.split()[:2]).upper(),
                    "first_name": name.split()[0] if name else f"C{i+1}",
                    "score": round(len(hit) / max(1, len(jw)), 2), "matched_terms": hit[:8]})
    return sorted(out, key=lambda x: -x["score"])

async def _hr_live(jd, resumes, top_k):
    async with streamablehttp_client(HR_MCP, timeout=30, sse_read_timeout=180) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            job = _tool_json(await s.call_tool("create_job", {"raw_text": jd}))
            job_id = job.get("id") or job.get("job_id")
            for txt in resumes:
                _tool_json(await s.call_tool("create_candidate", {"raw_text": txt}))
            ranked = _tool_json(await s.call_tool("rank_candidates", {"job_id": job_id, "top_k": top_k}))
            top = ranked[0] if isinstance(ranked, list) and ranked else {}
            cid = top.get("candidate_id") or top.get("id") or (top.get("candidate") or {}).get("id")
            draft = _tool_json(await s.call_tool("draft_email", {"candidate_id": cid, "job_id": job_id,
                                                                 "email_type": "outreach"})) if cid else {}
            return job, ranked, draft

def hr_run(body):
    task_id = body.get("task_id") or events.new_task_id("hr")
    parent = body.get("parent_id")
    A = body.get("actor") or "dev4-hr"
    jd = body.get("job_text") or DEFAULT_JD
    resumes = body.get("resumes") or _fixture_resumes()
    top_k = int(body.get("top_k", 3))
    mode = "live" if live() else "mock"
    events.emit("hr", task_id, "queued", f"HR: rank {len(resumes)} candidates for a role", mode,
                {"n_resumes": len(resumes)}, parent, A)
    import hr_extras
    extras = {}
    if body.get("write_jd") or body.get("role"):  # X01
        extras["jd"] = hr_extras.write_jd(body.get("role"), body.get("job_text") or jd, mode)
    blind = bool(body.get("blind"))
    blinded = None
    if blind:  # X02
        blinded, extras["fairness"] = hr_extras.blind(resumes)
    events.emit("hr", task_id, "running", "HR: " + ("blind " if blind else "") + "screening and ranking", mode,
                {"blind": blind, "jd_written": "jd" in extras}, parent, A)
    try:
        if mode == "live":
            job, ranked, draft = asyncio.run(_hr_live(jd, blinded if blind else resumes, top_k))
            shortlist = [{"candidate_id": (c.get("candidate_id") or c.get("id")),
                          "score": c.get("score"), "why": _scrub(str(c.get("explanation") or c.get("reason") or ""))[:240]}
                         for c in (ranked if isinstance(ranked, list) else [])][:top_k]
            body_txt = draft.get("body") if isinstance(draft, dict) else str(draft)
            subject = draft.get("subject", "") if isinstance(draft, dict) else ""
            engine = "open_recruiter MCP (LLM_PROVIDER=xai)"
        else:
            if blind:  # X02: rank on masked resumes, re-attach identity only for outreach
                ranked = _mock_rank(jd, blinded)[:top_k]
                for c in ranked:
                    orig = _mock_rank(jd, [resumes[int(c["candidate_id"].split("c")[-1]) - 1]])[0]
                    c["first_name"] = orig["first_name"]; c["initials"] = "--"
            else:
                ranked = _mock_rank(jd, resumes)[:top_k]
            shortlist = [{k: c[k] for k in ("candidate_id", "initials", "score", "matched_terms")} for c in ranked]
            top = ranked[0] if ranked else {"first_name": "there", "matched_terms": []}
            subject = "Quick chat about our first support hire?"
            body_txt = (f"Hi {top['first_name']},\n\nYour background in "
                        f"{', '.join(top['matched_terms'][:3]) or 'this area'} stood out for our founding support/ops role. "
                        "Would you be open to a 20-minute call this week?\n\nThanks,\nThe founder")
            engine = "MOCK: offline keyword-overlap heuristic (not open_recruiter, no LLM)"
    except Exception as e:
        events.emit("hr", task_id, "failed", f"HR live run failed: {type(e).__name__}", mode,
                    {"error": str(e)[:300]}, parent, A)
        return {"task_id": task_id, "mode": mode, "status": "failed", "error": str(e)[:300]}
    status, qr, body_txt = _gate("hr", task_id, "outbound_email", _scrub(body_txt or ""),
                                 "Founder asked HR to shortlist and draft first outreach.", parent, mode, A)
    out = {"engine": engine, "shortlist": shortlist, "outreach_draft": {"subject": subject, "body": body_txt},
           "qa": {"verdict": qr["verdict"], "score": qr["score"]}, **extras,
           "interview_kit": hr_extras.interview_kit(shortlist, jd, mode)}
    if body.get("role"): out["role"] = body["role"][:80]
    if body.get("revision_note"):
        out["revision_note"] = body["revision_note"][:300]; out["revision"] = int(body.get("revision", 1))
    events.emit("hr", task_id, status, f"HR: shortlist of {len(shortlist)} + outreach draft (QA {qr['verdict']})",
                mode, out, parent, A, needs_approval=(status == "needs_approval"))
    return {"task_id": task_id, "mode": mode, "status": status, **out, "qa": qr}

# ---------------- Design ----------------
# Brand-kit prompt structure adapted from Leonxlnx/imagegen-skills (MIT): subject / style / palette / type / composition / constraints.
def _palette(brand):
    h = hashlib.sha256(brand.encode()).hexdigest()
    base = [h[i:i+6] for i in (0, 6, 12, 18)]
    return ["#" + c for c in base] + ["#FFFFFF"]

def _brandkit_prompts(brand, brief, palette, n_posts):
    common = (f"Brand: {brand}. Brief: {brief}. Palette: {', '.join(palette)}. Typography: clean geometric sans. "
              "Constraints: no real people, no trademarks, no text other than the brand name, high contrast, flat vector.")
    p = [{"asset": "logo", "aspect_ratio": "1:1",
          "prompt": f"Minimal flat vector logo mark for '{brand}', single centered symbol plus wordmark, white background. {common}"}]
    for i in range(n_posts):
        p.append({"asset": f"social_post_{i+1}", "aspect_ratio": "1:1",
                  "prompt": f"Launch social post #{i+1} for '{brand}': bold abstract hero shape, generous whitespace, brand colors. {common}"})
    return p

def _mock_svg(path, brand, asset, palette):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512">'
           f'<rect width="512" height="512" fill="{palette[0]}"/><circle cx="256" cy="220" r="120" fill="{palette[1]}"/>'
           f'<text x="256" y="420" font-family="sans-serif" font-size="40" text-anchor="middle" fill="#fff">{brand}</text>'
           f'<text x="256" y="480" font-family="monospace" font-size="22" text-anchor="middle" fill="#fff">MOCK {asset} - not AI generated</text></svg>')
    open(path, "w").write(svg)

async def _design_live(prompts, outdir):
    env = dict(os.environ); env["XAI_API_KEY"] = os.environ["XAI_API_KEY"]
    params = StdioServerParameters(command="uv", args=["run", "--project", GROK_MCP_DIR, "python", f"{GROK_MCP_DIR}/main.py"],
                                   cwd=outdir, env=env)
    res = []
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            for p in prompts:
                out = await s.call_tool("generate_image", {"prompt": p["prompt"], "n": 1, "save": True,
                                                           "aspect_ratio": p["aspect_ratio"]})
                txt = "".join(getattr(c, "text", "") for c in out.content)
                if out.isError: raise RuntimeError(txt[:300])
                paths = re.findall(r"(\S+\.(?:png|jpg|jpeg|webp))", txt)
                res.append({"asset": p["asset"], "file": os.path.join(outdir, paths[0]) if paths and not paths[0].startswith("/") else (paths[0] if paths else None),
                            "tool_result": txt[:300]})
    return res

def design_run(body):
    task_id = body.get("task_id") or events.new_task_id("design")
    parent = body.get("parent_id")
    A = body.get("actor") or "dev4-design"
    brand = (body.get("brand") or "Acme Co").strip()[:40]
    brief = (body.get("brief") or "Launch visuals for a one-person company").strip()[:400]
    n_posts = max(0, min(2, int(body.get("n_posts", 2))))  # cap: logo + 2 posts = 3 images
    mode = "live" if live() else "mock"
    events.emit("design", task_id, "queued", f"Design: brand kit for {brand}", mode, {"n_assets": 1 + n_posts}, parent, A)
    events.emit("design", task_id, "running", "Design: building brand-kit prompts", mode, {}, parent, A)
    palette = _palette(brand)
    prompts = _brandkit_prompts(brand, brief, palette, n_posts)
    outdir = os.path.join(DESIGN_OUT, task_id); os.makedirs(outdir, exist_ok=True)
    try:
        if mode == "live":
            assets = asyncio.run(_design_live(prompts, outdir)); engine = "Grok-MCP generate_image (xAI)"
        else:
            assets = []
            for p in prompts:
                f = os.path.join(outdir, f"{p['asset']}.MOCK.svg"); _mock_svg(f, brand, p["asset"], palette)
                assets.append({"asset": p["asset"], "file": f})
            engine = "MOCK: local SVG placeholders (no image model called)"
            if body.get("force_low_score") and assets:  # X03 test hook: first logo deliberately off-brand
                _mock_svg(assets[0]["file"], brand, assets[0]["asset"], design_loop.OFF_BRAND)
    except Exception as e:
        events.emit("design", task_id, "failed", f"Design live run failed: {type(e).__name__}", mode,
                    {"error": str(e)[:300]}, parent, A)
        return {"task_id": task_id, "mode": mode, "status": "failed", "error": str(e)[:300]}
    def _regen(p):  # X03: one on-brand retry (lib/design_loop.py)
        if mode == "live": return asyncio.run(_design_live([p], outdir))[0]
        f = os.path.join(outdir, f"{p['asset']}.retry.MOCK.svg"); _mock_svg(f, brand, p["asset"], palette)
        return {"asset": p["asset"], "file": f}
    assets = design_loop.run(task_id, brand, brief, palette, prompts, assets, mode, parent, A, _regen, GROK_MCP_DIR)
    caption = body.get("caption") or f"Meet {brand}. {brief}. Launching this week."
    status, qr, caption = _gate("design", task_id, "public_post", caption, brief, parent, mode, A)
    out = {"engine": engine, "brand": brand, "palette": palette, "prompts": prompts, "assets": assets,
           "caption": caption, "qa": {"verdict": qr["verdict"], "score": qr["score"]}}
    events.emit("design", task_id, status, f"Design: {len(assets)} assets + caption (QA {qr['verdict']})",
                mode, {**{k: out[k] for k in ("engine", "brand", "palette", "assets", "caption", "qa")},
                       **({"revision_note": body["revision_note"][:300]} if body.get("revision_note") else {})}, parent,
                A, needs_approval=(status == "needs_approval"))
    return {"task_id": task_id, "mode": mode, "status": status, **out, "qa": qr}
