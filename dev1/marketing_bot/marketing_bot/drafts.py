"""Draft launch copy from brand voice + one skill file per content type."""
import json
import os
import re

from . import config

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+?\d{1,2}[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}\b")
DOLLAR_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?")
BANNED_RE = re.compile(
    r"(\b(?:as an ai language model|lorem ipsum|TODO|FIXME|act now|risk[- ]free|best in the world|"
    r"100% guaranteed|guarantee[ds]?|warrant\w*|refund\w*|discount\w*|coupon)\b|\[insert[^\]]*\])",
    re.I,
)

_SKILLS = ("x_post.md", "linkedin.md", "blog.md", "landing.md")


def load_voice():
    path = os.path.join(config.ROOT, "brand_voice.md")
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_skills():
    parts = []
    for name in _SKILLS:
        path = os.path.join(config.ROOT, "prompts", name)
        with open(path, encoding="utf-8") as f:
            parts.append(f"## {name}\n{f.read().strip()}")
    return "\n\n".join(parts)


def _clean(text):
    if not isinstance(text, str):
        return ""
    text = DOLLAR_RE.sub("the listed price", text)
    text = EMAIL_RE.sub("", text)
    text = PHONE_RE.sub("", text)
    text = BANNED_RE.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def _product(listing):
    product = listing.get("product") if isinstance(listing.get("product"), dict) else {}
    return {
        "type": str(product.get("type") or "merch"),
        "title": str(product.get("title") or "Pulse drop"),
        "tagline": _clean(str(product.get("tagline") or "")),
        "trend": str(product.get("trend") or listing.get("trend") or "this week's conversation"),
        "price": product.get("price"),
        "cost": product.get("cost"),
    }


def mock_drafts(listing, trend=None):
    """Template drafts. Labeled mock. Not AI-generated."""
    p = _product(listing)
    why = ""
    source = "x"
    if isinstance(trend, dict):
        why = _clean(str(trend.get("why") or ""))
        source = str(trend.get("source") or "x")
    why_bit = f" {why}" if why else ""
    title, kind, tagline, name = p["title"], p["type"], p["tagline"], p["trend"]
    tag = f" {tagline}" if tagline else ""
    x_post = _clean(f"{title} is live: a {kind} from the {name} conversation on X.{tag}")
    thread = [
        x_post,
        _clean(f"The {name} posts on X are what put this {kind} on the table.{why_bit}"),
        _clean("The listing has the details. This draft stays in the sandbox until a person posts it."),
    ]
    linkedin = _clean(
        f"People on X have been talking about {name}.{why_bit} "
        f"Pulse Studio turned that into {title}, a {kind}.{tag} "
        f"The drop is on the listing. This is a draft, not a published post."
    )
    blog = _clean(
        f"Draft: {title}\n\n"
        f"The conversation around {name} picked up on X (source: {source}).{why_bit}\n\n"
        f"Pulse Studio made {title}, a {kind}, from that conversation.{tag}\n\n"
        f"Open the listing to see the drop. Nothing here has been posted."
    )
    landing = {
        "headline": _clean(f"{title} is here"),
        "subhead": _clean(f"A {kind} drawn from the {name} conversation on X."),
        "bullets": [
            _clean(f"{kind.capitalize()} titled {title}."),
            _clean(tagline or f"Made from the {name} trend."),
            "Draft copy only. The listing has the rest.",
        ],
        "cta": "See the drop",
    }
    return _pack(x_post, thread, linkedin, blog, landing, "MOCK template (no XAI_API_KEY); not AI generated")


def _pack(x_post, thread, linkedin, blog, landing, engine):
    drafts = {
        "x_post": _clean(x_post),
        "x_thread": [_clean(x) for x in (thread or [])][:3],
        "linkedin": _clean(linkedin),
        "blog": _clean(blog),
        "landing": {
            "headline": _clean((landing or {}).get("headline") or ""),
            "subhead": _clean((landing or {}).get("subhead") or ""),
            "bullets": [_clean(b) for b in ((landing or {}).get("bullets") or [])][:3],
            "cta": _clean((landing or {}).get("cta") or "See the drop"),
        },
        "engine": engine,
        "posted": False,
        "sandbox": True,
    }
    if len(drafts["landing"]["bullets"]) < 3:
        drafts["landing"]["bullets"] += ["Open the listing for the drop."] * (3 - len(drafts["landing"]["bullets"]))
    if len(drafts["x_thread"]) < 2:
        drafts["x_thread"].append(drafts["x_post"])
    return drafts


def grok_drafts(grok, listing, trend=None):
    p = _product(listing)
    trend = trend or {}
    system = (
        load_voice()
        + "\n\nFollow every skill below. Return ONLY JSON with keys "
        "x_post (string), x_thread (array of 3 strings), linkedin (string), "
        "blog (string), landing (object with headline, subhead, bullets[3], cta).\n\n"
        + load_skills()
    )
    user = json.dumps({
        "brand": config.BRAND,
        "product": {k: p[k] for k in ("type", "title", "tagline", "trend")},
        "listing_url": listing.get("url") or "",
        "trend_spotted": {
            "trend": trend.get("trend") or p["trend"],
            "why": trend.get("why") or "",
            "source": trend.get("source") or "x",
        },
        "note": "Do not include a currency symbol, email, or phone. Price stays on the listing.",
    }, ensure_ascii=False)
    raw = grok.complete_json(system, user)
    landing = raw.get("landing") if isinstance(raw.get("landing"), dict) else {}
    return _pack(raw.get("x_post"), raw.get("x_thread"), raw.get("linkedin"), raw.get("blog"), landing,
                 f"grok:{grok.model}")


def public_content(drafts):
    """Primary X post only. Joining every channel made QA flag the copy as repetitive or mixed.
    LinkedIn, blog, thread, and landing stay on output.drafts."""
    return _clean((drafts or {}).get("x_post") or "")


def revise_mock(drafts, reasons):
    """One revision pass for template drafts: re-scrub and note the QA reasons were applied."""
    again = _pack(
        drafts.get("x_post"), drafts.get("x_thread"), drafts.get("linkedin"),
        drafts.get("blog"), drafts.get("landing"), drafts.get("engine") or "MOCK template",
    )
    again["revision"] = 1
    again["qa_reasons"] = [str(r)[:160] for r in (reasons or [])][:4]
    return again
