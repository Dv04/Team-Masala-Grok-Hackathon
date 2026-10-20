"""React to listing_live: running event immediately, then sandbox drafts through QA."""
import logging
import re
import threading

from . import config
from .clients import EventsClient, GrokClient
from .drafts import grok_drafts, mock_drafts, public_content, revise_mock

log = logging.getLogger("marketing")


def is_listing_live(ev):
    if not isinstance(ev, dict):
        return False
    out = ev.get("output") if isinstance(ev.get("output"), dict) else {}
    action = out.get("action") if isinstance(out.get("action"), dict) else {}
    kind = out.get("kind") or out.get("event") or action.get("kind") or action.get("type")
    return kind == "listing_live"


def listing_view(ev):
    """Normalize product, url, action from a listing_live event."""
    out = ev.get("output") if isinstance(ev.get("output"), dict) else {}
    action = out.get("action") if isinstance(out.get("action"), dict) else {}
    product = out.get("product") if isinstance(out.get("product"), dict) else None
    if product is None and isinstance(action.get("product"), dict):
        product = action["product"]
    return {
        "task_id": ev.get("task_id") or "",
        "dept": ev.get("dept") or "",
        "product": product or {},
        "url": out.get("url") or action.get("url") or "",
        "action": action or None,
        "assets": out.get("assets") or (product or {}).get("assets")
        or ([out["image_url"]] if out.get("image_url") else None),
        # dev2 / stand-in echoes of a design listing carry listing_task: one launch per product.
        "listing_task": out.get("listing_task") or ev.get("task_id") or "",
    }


def is_trend_spotted(ev):
    out = ev.get("output") if isinstance(ev.get("output"), dict) else {}
    return out.get("kind") == "trend_spotted" or out.get("event") == "trend_spotted"


def _safe_id(task_id):
    return re.sub(r"[^A-Za-z0-9_-]", "", task_id or "")[:48] or "listing"


class MarketingBot:
    def __init__(self, events=None, grok=None, drafter=None):
        self.events = events or EventsClient(config.DEPARTMENTS_URL)
        self.grok = grok if grok is not None else GrokClient(
            api_key=config.api_key(), model=config.TEXT_MODEL, base_url=config.XAI_BASE_URL)
        self._drafter = drafter
        self.seen = set()
        self.trends = []
        self._lock = threading.Lock()

    @property
    def mode(self):
        return "live" if self.grok.live else "mock"

    def register_webhook(self):
        """POST /api/webhooks. Log and continue if the service is down."""
        try:
            res = self.events.register_webhook(config.WEBHOOK_URL, config.DEPT)
            log.info("registered webhook %s dept=%s -> %s", config.WEBHOOK_URL, config.DEPT, res.get("ok", res))
            return res
        except Exception as e:
            log.warning("webhook register failed (continuing): %s", e)
            return None

    def announce(self):
        """One event so the marketing dashboard tile is connected before the first listing."""
        self._emit(
            "mkt-online", "done",
            "Marketing online; sandbox drafts only; watching listing_live",
            {"kind": "heartbeat", "webhook": config.WEBHOOK_URL, "posted": False},
        )

    def handle_event(self, ev):
        if not isinstance(ev, dict):
            return None
        with self._lock:
            if is_trend_spotted(ev):
                out = ev.get("output") or {}
                self.trends.append({
                    "trend": out.get("trend") or "",
                    "why": out.get("why") or "",
                    "source": out.get("source") or "x",
                    "task_id": ev.get("task_id"),
                })
            if not is_listing_live(ev):
                return None
            # Launch only on design's listing_live. Sales/engineering echoes often omit
            # listing_task, so the dept gate comes first; listing_task dedupe is the second guard.
            if (ev.get("dept") or "") != "design":
                return None
            key = listing_view(ev)["listing_task"]
            if not key or key in self.seen:
                return None
            self.seen.add(key)
            return self._launch(ev)

    def poll_once(self):
        try:
            data = self.events.list_events(limit=80)
        except Exception as e:
            log.warning("poll failed: %s", e)
            return []
        handled = []
        for ev in data.get("events") or []:
            result = self.handle_event(ev)
            if result:
                handled.append(result)
        return handled

    def _match_trend(self, product):
        want = str((product or {}).get("trend") or "").strip().lower()
        if not want:
            return None
        for t in reversed(self.trends):
            have = str(t.get("trend") or "").strip().lower()
            if have and (have == want or want in have or have in want):
                return t
        return None

    def _draft(self, listing, trend, qa_reasons=None):
        if self._drafter:
            return self._drafter(listing, trend, qa_reasons)
        if self.grok.live:
            try:
                drafts = grok_drafts(self.grok, listing, trend)
                if qa_reasons:
                    drafts["revision"] = 1
                    drafts["qa_reasons"] = [str(r)[:160] for r in qa_reasons][:4]
                return drafts
            except Exception as e:
                log.warning("Grok draft failed, using labeled mock: %s", e)
        drafts = mock_drafts(listing, trend)
        if qa_reasons:
            drafts = revise_mock(drafts, qa_reasons)
        return drafts

    def _launch(self, ev):
        listing = listing_view(ev)
        task_id = f"mkt-{_safe_id(listing['listing_task'])}"
        parent = listing["listing_task"] or None
        product = listing["product"]
        title = product.get("title") or "listing"
        trend = self._match_trend(product)
        # Stand-in window is ~8s. Post running before any model call.
        self._emit(task_id, "running", f"Marketing drafting launch copy for {title}", {
            "kind": "marketing_draft", "trigger": "listing_live", "posted": False, "sandbox": True,
        }, parent=parent)
        if not listing.get("assets"):
            brief = (
                f"Launch creative for {product.get('product_type') or product.get('type') or 'merch'}: {title}. "
                f"Trend: {product.get('trend') or ''}. Tagline: {product.get('tagline') or ''}."
            ).strip()
            self._emit(f"{task_id}-design", "done", f"Design request for {title}", {
                "kind": "design_request",
                "brand": config.BRAND,
                "brief": brief[:400],
            }, parent=task_id)
        mode = "live" if self.grok.live else "mock"
        drafts = self._draft(listing, trend)
        if not str(drafts.get("engine") or "").startswith("grok:"):
            mode = "mock"
        content = public_content(drafts)
        context = f"trend={product.get('trend') or ''}; title={title}; url={listing.get('url') or ''}"
        verdict = self._qa(task_id, content, context, parent, mode)
        if verdict and verdict.get("verdict") == "fail":
            self._emit(task_id, "running", "Marketing revising draft after QA fail", {
                "kind": "marketing_revise", "qa_reasons": (verdict.get("reasons") or [])[:4],
            }, parent=parent)
            drafts = self._draft(listing, trend, verdict.get("reasons") or [])
            if not str(drafts.get("engine") or "").startswith("grok:"):
                mode = "mock"
            content = public_content(drafts)
            verdict = self._qa(task_id, content, context, parent, mode)
        status, needs = _status_for(verdict)
        output = {
            # /api/qa/check already ran above. False so the hub does not QA this post a second time.
            "needs_qa": False,
            "kind": "public_post",
            "content": content,
            "context": context,
            "drafts": drafts,
            "listing_url": listing.get("url") or "",
            "product": {k: product.get(k) for k in ("type", "title", "tagline", "trend")},
            "posted": False,
            "sandbox": True,
            "qa": {"verdict": (verdict or {}).get("verdict"), "score": (verdict or {}).get("score")},
        }
        summary = f"Marketing drafts for {title} ({status}, sandbox, not posted)"
        self._emit(task_id, status, summary, output, parent=parent, needs_approval=needs)
        return {"task_id": task_id, "status": status, "mode": mode, "drafts": drafts, "qa": verdict}

    def _qa(self, task_id, content, context, parent, mode):
        body = {
            "dept": config.DEPT, "task_id": task_id, "kind": "public_post",
            "content": content, "context": context, "mode": mode,
        }
        if parent:
            body["parent_id"] = parent
        try:
            return self.events.qa_check(body)
        except Exception as e:
            log.warning("qa.check failed: %s", e)
            return None

    def _emit(self, task_id, status, summary, output, parent=None, needs_approval=None):
        ev = {
            "dept": config.DEPT,
            "task_id": task_id,
            "actor": config.ACTOR,
            "status": status,
            "summary": summary[:200],
            "mode": "live" if self.grok.live and str((output or {}).get("engine") or "").startswith("grok:") else (
                "mock" if status != "running" and not self.grok.live else self._emit_mode(output)
            ),
            "output": output or {},
        }
        # Running/heartbeat before a draft exists: honest about whether a key is set.
        if status in ("running", "done") and not (output or {}).get("drafts"):
            ev["mode"] = "live" if self.grok.live else "mock"
        if (output or {}).get("drafts"):
            engine = str(((output or {}).get("drafts") or {}).get("engine") or "")
            ev["mode"] = "live" if engine.startswith("grok:") else "mock"
        if parent:
            ev["parent_id"] = parent
        if needs_approval is not None:
            ev["needs_approval"] = needs_approval
        try:
            return self.events.post_event(ev)
        except Exception as e:
            log.warning("event post failed: %s", e)
            return None

    def _emit_mode(self, output):
        return "live" if self.grok.live else "mock"


def _status_for(verdict):
    name = (verdict or {}).get("verdict")
    if name == "pass":
        return "done", False
    if name == "founder":
        return "needs_approval", True
    if name == "fail":
        # Second fail on the same task is the founder's. If the gate still says fail, stop.
        return "needs_approval", True
    # QA unreachable: do not pretend the copy was approved.
    return "failed", False
