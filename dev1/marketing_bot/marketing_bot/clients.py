"""Self-contained department + Grok clients.

dev1/common/ was not on dev1 or main when this bot was written. Swap these
for the shared client when it lands; MarketingBot only needs post_event,
list_events, register_webhook, and qa_check.

LLM calls use httpx. Default host is https://api.x.ai/v1, overridable via XAI_BASE_URL for the xAI budget proxy. Mock when XAI_API_KEY is unset.
"""
import json
import os
import urllib.parse

import httpx

# Reasoning models reject these. Never send them.
_BANNED_BODY_KEYS = ("stop", "presence_penalty", "frequency_penalty", "presencePenalty", "frequencyPenalty")
DEFAULT_XAI_BASE = "https://api.x.ai/v1"


def xai_base() -> str:
    """Default https://api.x.ai/v1, overridable via XAI_BASE_URL for the xAI budget proxy."""
    return os.environ.get("XAI_BASE_URL", DEFAULT_XAI_BASE).rstrip("/")


class HttpError(RuntimeError):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status
        self.body = body


def httpx_transport(method, url, body=None, headers=None, timeout=15):
    req_headers = dict(headers or {})
    try:
        res = httpx.request(method, url, json=body, headers=req_headers, timeout=timeout)
    except httpx.HTTPError as e:
        raise HttpError(0, str(e)) from None
    if res.status_code >= 400:
        raise HttpError(res.status_code, res.text)
    if not res.content:
        return {}
    return res.json()


class EventsClient:
    def __init__(self, base_url, transport=None):
        self.base = base_url.rstrip("/")
        self.transport = transport or httpx_transport

    def post_event(self, ev):
        # The service sets ts. Dept-specific fields belong in output.
        body = {k: v for k, v in ev.items() if k != "ts" and v is not None}
        return self.transport("POST", f"{self.base}/api/events", body)

    def list_events(self, limit=100, dept=None, task_id=None):
        q = {"limit": str(limit)}
        if dept:
            q["dept"] = dept
        if task_id:
            q["task_id"] = task_id
        return self.transport("GET", f"{self.base}/api/events?{urllib.parse.urlencode(q)}")

    def register_webhook(self, url, dept):
        return self.transport("POST", f"{self.base}/api/webhooks", {"url": url, "dept": dept})

    def qa_check(self, body):
        return self.transport("POST", f"{self.base}/api/qa/check", body)


class GrokClient:
    """xAI chat completions. Default host is https://api.x.ai/v1, overridable via XAI_BASE_URL for the xAI budget proxy. Mock when no API key."""

    def __init__(self, api_key="", model="grok-4", base_url=None, transport=None):
        if not str(model).startswith("grok-"):
            raise ValueError("model must be a grok-* model")
        allowed = {DEFAULT_XAI_BASE, xai_base()}
        if base_url is None:
            chosen = xai_base()
        else:
            chosen = str(base_url).rstrip("/")
            if chosen not in allowed:
                raise ValueError("base_url must be https://api.x.ai/v1 or XAI_BASE_URL")
        self.api_key = api_key or ""
        self.model = model
        self.base_url = chosen
        self.transport = transport or httpx_transport

    @property
    def live(self):
        return bool(self.api_key)

    def complete_json(self, system, user):
        if not self.live:
            raise RuntimeError("mock mode: XAI_API_KEY is not set")
        body = {
            "model": self.model,
            "temperature": 0.4,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        for k in _BANNED_BODY_KEYS:
            body.pop(k, None)
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = self.transport("POST", f"{self.base_url}/chat/completions", body, headers=headers, timeout=45)
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
