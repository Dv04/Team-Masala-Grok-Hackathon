"""POST /api/events. The departments service owns timestamps. mode is live only with a key."""
import json
import re

import httpx

from .config import Settings, load_settings

STATUSES = {"queued", "running", "needs_approval", "approved", "rejected", "done", "failed"}
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+?\d{1,2}[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}\b")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
SECRET_RE = re.compile(r"(xai-[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,})")


class EventError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def redact(text: str) -> str:
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    text = SECRET_RE.sub("[redacted]", text)
    text = SSN_RE.sub("[redacted]", text)
    text = EMAIL_RE.sub("[redacted]", text)
    text = PHONE_RE.sub("[redacted]", text)
    return text


def _http_json(method: str, url: str, payload: dict | None, timeout: float):
    headers = {"accept": "application/json"}
    kwargs = {"headers": headers, "timeout": timeout}
    if payload is not None:
        kwargs["json"] = payload
    try:
        resp = httpx.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise EventError(f"departments service unreachable: {type(exc).__name__}") from None
    try:
        parsed = resp.json()
    except ValueError:
        parsed = {"error": resp.text[:300]}
    return resp.status_code, parsed


class EventsClient:
    def __init__(self, settings: Settings | None = None, sender=None):
        self.settings = settings or load_settings()
        self._sender = sender

    def honest_mode(self, mode: str) -> str:
        if mode == "live" and self.settings.live:
            return "live"
        return "mock"

    def post_event(
        self,
        *,
        dept: str,
        task_id: str,
        status: str,
        summary: str,
        mode: str,
        actor: str,
        output: dict | None = None,
        parent_id: str | None = None,
        timeout: float = 15,
    ) -> dict:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {sorted(STATUSES)}")
        if mode not in ("live", "mock"):
            raise ValueError("mode must be 'live' or 'mock'")
        if not dept or not task_id or not summary or not actor:
            raise ValueError("dept, task_id, summary, and actor are required")
        body = {
            "dept": dept.strip().lower(),
            "task_id": task_id,
            "status": status,
            "summary": redact(summary)[:400],
            "mode": self.honest_mode(mode),
            "actor": actor,
            "output": output or {},
        }
        if parent_id:
            body["parent_id"] = parent_id
        blob = json.dumps(body)
        if SECRET_RE.search(blob):
            raise EventError("refusing to post an event that still contains a secret")
        if self._sender:
            return self._sender(body)
        status_code, parsed = _http_json(
            "POST", self.settings.departments_base_url + "/api/events", body, timeout
        )
        if status_code >= 400:
            err = parsed.get("error") if isinstance(parsed, dict) else parsed
            raise EventError(f"POST /api/events failed: {err}"[:300], status_code)
        return parsed

    def get_events(self, *, task_id: str | None = None, dept: str | None = None, limit: int = 50, timeout: float = 15) -> dict:
        params = {k: v for k, v in {"task_id": task_id, "dept": dept, "limit": str(limit)}.items() if v}
        qs = str(httpx.QueryParams(params))
        url = self.settings.departments_base_url + "/api/events" + (("?" + qs) if qs else "")
        status_code, parsed = _http_json("GET", url, None, timeout)
        if status_code >= 400:
            raise EventError(f"GET /api/events failed ({status_code})", status_code)
        return parsed
