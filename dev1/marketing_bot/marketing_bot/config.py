"""Env config. No secrets are read from disk."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPT = "marketing"
ACTOR = "dev1-marketing"
BRAND = "Pulse Studio"

DEPARTMENTS_URL = os.environ.get("DEPARTMENTS_URL", "http://127.0.0.1:8810").rstrip("/")
WEBHOOK_URL = os.environ.get("MARKETING_WEBHOOK_URL", "http://127.0.0.1:8899/pulse")
HOST = os.environ.get("MARKETING_HOST", "127.0.0.1")
PORT = int(os.environ.get("MARKETING_PORT", "8899"))
POLL_SEC = float(os.environ.get("MARKETING_POLL_SEC", "2"))

XAI_BASE_URL = os.environ.get("XAI_BASE_URL", "https://api.x.ai/v1").rstrip("/")
# Team default is grok-4. Override with GROK_TEXT_MODEL / GROK_FAST_MODEL.
TEXT_MODEL = os.environ.get("GROK_TEXT_MODEL") or "grok-4"
FAST_MODEL = os.environ.get("GROK_FAST_MODEL") or TEXT_MODEL


def api_key():
    return os.environ.get("XAI_API_KEY") or ""


def mode():
    """Honest mode: live only when a key is present and a draft actually came from Grok."""
    return "live" if api_key() else "mock"
