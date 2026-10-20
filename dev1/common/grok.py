"""xAI Responses API only. Default host is https://api.x.ai/v1, overridable via XAI_BASE_URL for the xAI budget proxy. No call is made when XAI_API_KEY is empty."""
import json
import logging
import os

import httpx

from .config import Settings, load_settings

log = logging.getLogger("grok")


def xai_base() -> str:
    """Default https://api.x.ai/v1, overridable via XAI_BASE_URL for the xAI budget proxy."""
    return os.environ.get("XAI_BASE_URL", "https://api.x.ai/v1").rstrip("/")


def _error_body(data, secret: str = "") -> str:
    """Truncated response body for logs. Never includes the API key."""
    if isinstance(data, (dict, list)):
        text = json.dumps(data, default=str)
    else:
        text = "" if data is None else str(data)
    if secret:
        text = text.replace(secret, "[redacted]")
    return text[:300]


class GrokError(Exception):
    pass


class GrokResult:
    def __init__(self, text: str, mode: str, model: str, mock: bool):
        self.text = text
        self.mode = mode
        self.model = model
        self.mock = mock


def grok_model(name: str) -> str:
    model = (name or "").strip()
    if not model.startswith("grok-"):
        raise GrokError("refusing a non-grok model name")
    return model


def _extract_text(data: dict) -> str:
    if isinstance(data.get("output_text"), str) and data["output_text"].strip():
        return data["output_text"]
    parts = []
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message":
            for chunk in item.get("content") or []:
                if isinstance(chunk, dict) and chunk.get("text"):
                    parts.append(chunk["text"])
        elif isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts)


class GrokClient:
    def __init__(self, settings: Settings | None = None, sender=None):
        self.settings = settings or load_settings()
        self._sender = sender

    @property
    def mode(self) -> str:
        return "live" if self.settings.live else "mock"

    def respond(self, prompt: str, *, tools: list | None = None, fast: bool = False, timeout: float = 50) -> GrokResult:
        model = grok_model(self.settings.fast_model if fast else self.settings.text_model)
        if not self.settings.live:
            return GrokResult(text="", mode="mock", model=model, mock=True)
        payload = {"model": model, "input": prompt, "tools": tools or []}
        url = xai_base() + "/responses"
        if self._sender:
            status, data = self._sender(url, payload, self.settings.xai_api_key)
        else:
            status, data = self._post(url, payload, timeout)
        if status >= 400:
            log.warning("xAI responses HTTP %s: %s", status, _error_body(data, self.settings.xai_api_key))
            raise GrokError(f"xAI responses HTTP {status}")
        if not isinstance(data, dict):
            raise GrokError("xAI responses returned a non-object")
        return GrokResult(text=_extract_text(data), mode="live", model=model, mock=False)

    def _post(self, url: str, payload: dict, timeout: float):
        try:
            resp = httpx.post(
                url,
                json=payload,
                headers={
                    "accept": "application/json",
                    "authorization": f"Bearer {self.settings.xai_api_key}",
                },
                timeout=timeout,
            )
        except httpx.HTTPError as exc:
            raise GrokError(f"xAI unreachable: {type(exc).__name__}") from None
        raw = resp.text or ""
        try:
            data = resp.json()
        except ValueError:
            data = {"error": raw[:300]}
        return resp.status_code, data
