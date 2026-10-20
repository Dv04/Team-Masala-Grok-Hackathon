"""Self-contained department + Grok clients.

dev1/common/ was not on dev1 or main when this bot was written. Swap these
for the shared client when it lands; MarketingBot only needs post_event,
list_events, register_webhook, and qa_check.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

# Reasoning models reject these. Never send them.
_BANNED_BODY_KEYS = ("stop", "presence_penalty", "frequency_penalty", "presencePenalty", "frequencyPenalty")


class HttpError(RuntimeError):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status
        self.body = body


def urllib_transport(method, url, body=None, headers=None, timeout=15):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if body is not None:
        req.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise HttpError(e.code, detail) from None


class EventsClient:
    def __init__(self, base_url, transport=None):
        self.base = base_url.rstrip("/")
        self.transport = transport or urllib_transport

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
    """Chat completions against https://api.x.ai/v1. Mock when no API key."""

    def __init__(self, api_key="", model="grok-4", base_url="https://api.x.ai/v1", transport=None):
        self.api_key = api_key or ""
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.transport = transport or urllib_transport

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
