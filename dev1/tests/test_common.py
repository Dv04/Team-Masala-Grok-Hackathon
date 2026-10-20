"""Offline tests for the shared client. No network."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.config import Settings, load_settings
from common.events import EventError, EventsClient, redact
from common.grok import GrokClient, GrokError


def _settings(**kwargs) -> Settings:
    base = dict(
        xai_api_key="",
        text_model="grok-4",
        fast_model="grok-4-fast-test",
        image_model="grok-imagine-image-2.0",
        departments_base_url="http://127.0.0.1:8810",
    )
    base.update(kwargs)
    return Settings(**base)


class ConfigTests(unittest.TestCase):
    def test_defaults_when_env_empty(self):
        keys = ["XAI_API_KEY", "GROK_TEXT_MODEL", "GROK_FAST_MODEL", "GROK_IMAGE_MODEL", "DEPARTMENTS_BASE_URL"]
        saved = {k: os.environ.get(k) for k in keys}
        try:
            for key in keys:
                os.environ.pop(key, None)
            settings = load_settings()
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        self.assertEqual(settings.text_model, "grok-4")
        self.assertEqual(settings.fast_model, "grok-4")
        self.assertEqual(settings.image_model, "grok-imagine-image-2.0")
        self.assertEqual(settings.departments_base_url, "http://127.0.0.1:8810")
        self.assertFalse(settings.live)


class GrokTests(unittest.TestCase):
    def setUp(self):
        self._saved_base = os.environ.pop("XAI_BASE_URL", None)

    def tearDown(self):
        if self._saved_base is None:
            os.environ.pop("XAI_BASE_URL", None)
        else:
            os.environ["XAI_BASE_URL"] = self._saved_base

    def test_default_base_is_api_xai(self):
        seen = {}

        def sender(url, payload, key):
            seen["url"] = url
            return 200, {"output_text": "ok"}

        GrokClient(_settings(xai_api_key="test-key"), sender=sender).respond("hi")
        self.assertEqual(seen["url"], "https://api.x.ai/v1/responses")
        self.assertNotIn("test-key", seen["url"])

    def test_xai_base_url_env_override_is_used(self):
        os.environ["XAI_BASE_URL"] = "http://127.0.0.1:9/v1/"
        seen = {}

        def sender(url, payload, key):
            seen["url"] = url
            seen["key"] = key
            return 200, {"output_text": "ok"}

        GrokClient(_settings(xai_api_key="test-key"), sender=sender).respond("hi")
        self.assertEqual(seen["url"], "http://127.0.0.1:9/v1/responses")
        self.assertEqual(seen["key"], "test-key")
        self.assertNotIn("test-key", seen["url"])

    def test_mock_does_not_call_network(self):
        def sender(url, payload, key):
            raise AssertionError("mock mode must not call xAI")

        result = GrokClient(_settings(), sender=sender).respond("hi", tools=[{"type": "x_search"}])
        self.assertTrue(result.mock)
        self.assertEqual(result.mode, "mock")
        self.assertEqual(result.text, "")

    def test_live_request_shape(self):
        seen = {}

        def sender(url, payload, key):
            seen["url"] = url
            seen["payload"] = payload
            seen["key"] = key
            return 200, {"output_text": '{"trend":"Frogs","why":"Hats."}'}

        client = GrokClient(_settings(xai_api_key="test-key"), sender=sender)
        result = client.respond("find a trend", tools=[{"type": "x_search"}, {"type": "web_search"}])
        self.assertEqual(result.mode, "live")
        self.assertIn("Frogs", result.text)
        self.assertEqual(seen["url"], "https://api.x.ai/v1/responses")
        self.assertEqual(seen["key"], "test-key")
        self.assertEqual(seen["payload"]["model"], "grok-4")
        self.assertEqual([t["type"] for t in seen["payload"]["tools"]], ["x_search", "web_search"])
        for banned in ("stop", "presence_penalty", "frequency_penalty"):
            self.assertNotIn(banned, seen["payload"])

    def test_fast_model_flag(self):
        seen = {}

        def sender(url, payload, key):
            seen["model"] = payload["model"]
            return 200, {"output": [{"type": "message", "content": [{"type": "output_text", "text": "ok"}]}]}

        result = GrokClient(_settings(xai_api_key="test-key"), sender=sender).respond("x", fast=True)
        self.assertEqual(seen["model"], "grok-4-fast-test")
        self.assertEqual(result.text, "ok")

    def test_refuses_non_grok_model_without_calling_out(self):
        def sender(url, payload, key):
            raise AssertionError("non-grok model must not be sent")

        client = GrokClient(_settings(xai_api_key="test-key", text_model="local-model"), sender=sender)
        with self.assertRaises(GrokError):
            client.respond("hi")


class EventTests(unittest.TestCase):
    def test_omits_timestamp_and_coerces_live_without_key(self):
        seen = {}

        def sender(body):
            seen["body"] = body
            return {"ok": True, "event": body}

        client = EventsClient(_settings(), sender=sender)
        client.post_event(
            dept="Research",
            task_id="trend-1",
            status="done",
            summary="Trend spotted",
            mode="live",
            actor="dev1-trend",
            output={"kind": "trend_spotted", "source": "x"},
        )
        body = seen["body"]
        self.assertNotIn("ts", body)
        self.assertEqual(body["mode"], "mock")
        self.assertEqual(body["dept"], "research")
        self.assertEqual(body["status"], "done")

    def test_live_kept_when_key_present(self):
        seen = {}
        EventsClient(_settings(xai_api_key="test-key"), sender=lambda body: seen.update(body=body) or body).post_event(
            dept="research", task_id="t", status="done", summary="s", mode="live", actor="dev1-trend"
        )
        self.assertEqual(seen["body"]["mode"], "live")

    def test_rejects_bad_status_and_secrets(self):
        client = EventsClient(_settings(), sender=lambda body: body)
        with self.assertRaises(ValueError):
            client.post_event(dept="research", task_id="t", status="sent", summary="s", mode="mock", actor="a")
        with self.assertRaises(EventError):
            client.post_event(
                dept="research",
                task_id="t",
                status="done",
                summary="s",
                mode="mock",
                actor="a",
                output={"leak": "sk-" + "a" * 24},
            )

    def test_redact_contact_and_secret(self):
        cleaned = redact("mail a@b.co phone 512-555-0100 ssn 123-45-6789 key sk-" + "b" * 24)
        self.assertNotIn("a@b.co", cleaned)
        self.assertNotIn("512-555-0100", cleaned)
        self.assertNotIn("123-45-6789", cleaned)
        self.assertNotIn("sk-", cleaned)


if __name__ == "__main__":
    unittest.main()
