"""X03 (W2): Design generate -> score -> retry on-brand loop.
Pattern from google/adk-recipes on-brand-genmedia (Apache-2.0): score each generated asset against the brief and
regenerate once if it is below THRESHOLD. Only the pattern is reused; no code and no GCP.
- mock (no XAI_API_KEY): deterministic rule check of the SVG: brand palette colours present, brand name present,
  512x512 size, MOCK label present. Labeled scorer="MOCK rule check (not a vision model)".
- live: Grok-MCP chat_with_vision rates the image 0..1 against the brief (UNTESTED until the key exists; any error
  -> brand_score None, scorer says why, never a made-up number).
Exactly one regenerate per asset, max. Each regenerate logs one `running` event with output.kind="design_regenerate".
Test hook: body force_low_score:true makes the FIRST logo attempt deliberately off-brand (wrong palette), so the
low score is real for that file, then the retry uses the brand palette.
"""
import asyncio, json, os, re
import events

THRESHOLD = 0.7
MOCK_SCORER = "MOCK rule check (palette, brand name, size, MOCK label; not a vision model)"
OFF_BRAND = ["#777777", "#888888", "#999999", "#AAAAAA", "#FFFFFF"]


def mock_score(path, brand, palette):
    try:
        svg = open(path).read()
    except Exception as e:
        return None, [f"unreadable: {type(e).__name__}"]
    checks = {
        "primary colour": palette[0].lower() in svg.lower(),
        "secondary colour": palette[1].lower() in svg.lower(),
        "brand name": brand in svg,
        "512x512": 'width="512"' in svg and 'height="512"' in svg,
        "MOCK label": "MOCK" in svg,
    }
    score = round(sum(checks.values()) / len(checks), 2)
    return score, [f"{'ok' if v else 'missing'}: {k}" for k, v in checks.items()]


async def _vision(path, brand, brief, palette, grok_dir):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command="uv", args=["run", "--project", grok_dir, "python", f"{grok_dir}/main.py"],
                                   cwd=os.path.dirname(path), env=dict(os.environ))
    prompt = (f"Rate how on-brand this image is for brand '{brand}' (palette {', '.join(palette[:4])}; brief: {brief}). "
              'Reply ONLY with JSON {"score": <0..1>, "reasons": ["..."]}.')
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            out = await s.call_tool("chat_with_vision", {"prompt": prompt, "image_paths": [path]})
            txt = "".join(getattr(c, "text", "") for c in out.content)
            if out.isError: raise RuntimeError(txt[:200])
    m = re.search(r"\{.*\}", txt, re.S)
    j = json.loads(m.group(0)) if m else {}
    return max(0.0, min(1.0, float(j["score"]))), [str(x)[:120] for x in j.get("reasons", [])][:4]


def score(path, brand, brief, palette, mode, grok_dir):
    if mode == "mock":
        s, reasons = mock_score(path, brand, palette)
        return s, reasons, MOCK_SCORER
    if not path or not re.search(r"\.(png|jpe?g)$", path, re.I):
        return None, ["vision scorer needs png/jpg"], "Grok-MCP chat_with_vision (skipped)"
    try:
        s, reasons = asyncio.run(_vision(path, brand, brief, palette, grok_dir))
        return s, reasons, "Grok-MCP chat_with_vision (xAI)"
    except Exception as e:
        return None, [f"vision scoring failed: {type(e).__name__}: {str(e)[:120]}"], "Grok-MCP chat_with_vision (error)"


def run(task_id, brand, brief, palette, prompts, assets, mode, parent, actor, regen, grok_dir):
    """Score every asset; regenerate once if below THRESHOLD. regen(prompt_dict) -> new asset dict. Returns assets
    with brand_score, brand_reasons, brand_scorer, attempts."""
    by_asset = {p["asset"]: p for p in prompts}
    out = []
    for a in assets:
        s, reasons, scorer = score(a.get("file"), brand, brief, palette, mode, grok_dir)
        a = {**a, "brand_score": s, "brand_reasons": reasons, "brand_scorer": scorer, "attempts": 1}
        if s is not None and s < THRESHOLD and a["asset"] in by_asset:
            events.emit("design", task_id, "running",
                        f"Design: {a['asset']} brand score {s} < {THRESHOLD}, regenerating once", mode,
                        {"kind": "design_regenerate", "asset": a["asset"], "brand_score": s, "brand_reasons": reasons,
                         "brand_scorer": scorer, "threshold": THRESHOLD}, parent, actor)
            try:
                b = regen(by_asset[a["asset"]])
                s2, r2, sc2 = score(b.get("file"), brand, brief, palette, mode, grok_dir)
                a = {**b, "brand_score": s2, "brand_reasons": r2, "brand_scorer": sc2, "attempts": 2,
                     "first_score": s}
            except Exception as e:
                a["brand_reasons"] = reasons + [f"regenerate failed: {type(e).__name__}"]
        out.append(a)
    return out
