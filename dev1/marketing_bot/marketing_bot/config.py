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

# Default https://api.x.ai/v1, overridable via XAI_BASE_URL for the xAI budget proxy.
# Read on each access so a process started with the proxy env picks it up at call time.
_DEFAULT_XAI_BASE = "https://api.x.ai/v1"


def xai_base_url():
    return os.environ.get("XAI_BASE_URL", _DEFAULT_XAI_BASE).rstrip("/")


def __getattr__(name):
    if name == "XAI_BASE_URL":
        return xai_base_url()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _grok_model(env_name, default):
    raw = (os.environ.get(env_name) or "").strip()
    if not raw:
        return default
    if not raw.startswith("grok-"):
        raise RuntimeError(f"{env_name} must be a grok-* model")
    return raw


TEXT_MODEL = _grok_model("GROK_TEXT_MODEL", "grok-4")
FAST_MODEL = _grok_model("GROK_FAST_MODEL", "grok-4")
IMAGE_MODEL = _grok_model("GROK_IMAGE_MODEL", "grok-imagine-image-2.0")


def api_key():
    return os.environ.get("XAI_API_KEY") or ""


def mode():
    """Honest mode: live only when a key is present and a draft actually came from Grok."""
    return "live" if api_key() else "mock"
