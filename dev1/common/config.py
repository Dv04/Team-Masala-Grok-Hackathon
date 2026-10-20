"""Env config. The key is read from the environment and never written to disk."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    xai_api_key: str
    text_model: str
    fast_model: str
    image_model: str
    departments_base_url: str

    @property
    def live(self) -> bool:
        return bool(self.xai_api_key)


def load_settings() -> Settings:
    return Settings(
        xai_api_key=os.environ.get("XAI_API_KEY", "").strip(),
        text_model=os.environ.get("GROK_TEXT_MODEL", "grok-4").strip() or "grok-4",
        fast_model=os.environ.get("GROK_FAST_MODEL", "grok-4").strip() or "grok-4",
        image_model=os.environ.get("GROK_IMAGE_MODEL", "grok-imagine-image-2.0").strip() or "grok-imagine-image-2.0",
        departments_base_url=os.environ.get("DEPARTMENTS_BASE_URL", "http://127.0.0.1:8810").strip().rstrip("/"),
    )
