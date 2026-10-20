"""Offline Trend bot tests. No network and no XAI key."""
import unittest

from common.config import Settings
from common.grok import GrokError
from trend_bot.bot import load_backup, parse_trend, spot


def _settings(**kwargs) -> Settings:
    base = dict(
        xai_api_key="",
        text_model="grok-4",
        fast_model="grok-4",
        image_model="grok-imagine-image-2.0",
        departments_base_url="http://127.0.0.1:8810",
    )
    base.update(kwargs)
    return Settings(**base)


class TrendTests(unittest.TestCase):
    def _run(self, settings, grok_sender=None):
        posted = {}

        def events_sender(body):
            posted["body"] = body
            return {"ok": True, "event": {**body, "ts": "server-set"}}

        from common.events import EventsClient
        from common.grok import GrokClient

        result = spot(
            settings=settings,
            grok=GrokClient(settings, sender=grok_sender),
            events=EventsClient(settings, sender=events_sender),
        )
        return result, posted["body"]

    def test_no_key_uses_backup_and_does_not_call_grok(self):
        def grok_sender(url, payload, key):
            raise AssertionError("no key means no HTTP")

        backup_trend, backup_why = load_backup()
        result, body = self._run(_settings(), grok_sender)
        self.assertTrue(result["fallback"])
        self.assertEqual(result["mode"], "mock")
        self.assertEqual(body["dept"], "research")
        self.assertEqual(body["actor"], "dev1-trend")
        self.assertEqual(body["status"], "done")
        self.assertEqual(body["mode"], "mock")
        self.assertNotIn("ts", body)
        self.assertEqual(body["output"]["kind"], "trend_spotted")
        self.assertEqual(body["output"]["source"], "x")
        self.assertEqual(body["output"]["trend"], backup_trend)
        self.assertEqual(body["output"]["why"], backup_why)
        self.assertEqual(body["output"]["fallback"], "backup_fixture")
        self.assertTrue(body["task_id"].startswith("trend-"))

    def test_live_parse_keeps_source_x(self):
        def grok_sender(url, payload, key):
            self.assertIn("x_search", [t["type"] for t in payload["tools"]])
            self.assertNotIn("stop", payload)
            return 200, {"output_text": '```json\n{"trend":"Pixel frogs","why":"X wants frog stickers."}\n```'}

        result, body = self._run(_settings(xai_api_key="test-key"), grok_sender)
        self.assertFalse(result["fallback"])
        self.assertEqual(body["mode"], "live")
        self.assertEqual(body["output"]["trend"], "Pixel frogs")
        self.assertEqual(body["output"]["why"], "X wants frog stickers.")
        self.assertEqual(body["output"]["source"], "x")
        self.assertNotIn("fallback", body["output"])

    def test_grok_failure_falls_back_mock(self):
        def grok_sender(url, payload, key):
            raise GrokError("xAI responses HTTP 500")

        result, body = self._run(_settings(xai_api_key="test-key"), grok_sender)
        self.assertTrue(result["fallback"])
        self.assertEqual(body["mode"], "mock")
        self.assertEqual(body["output"]["trend"], load_backup()[0])
        self.assertEqual(body["output"]["source"], "x")

    def test_pii_in_model_text_is_not_posted_raw(self):
        def grok_sender(url, payload, key):
            return 200, {"output_text": '{"trend":"Frog hats","why":"Email frog@example.com or call 512-555-0199."}'}

        _result, body = self._run(_settings(xai_api_key="test-key"), grok_sender)
        self.assertNotIn("frog@example.com", json_dump := __import__("json").dumps(body))
        self.assertNotIn("512-555-0199", json_dump)
        self.assertEqual(body["mode"], "live")

    def test_parse_rejects_empty(self):
        self.assertIsNone(parse_trend("not json"))
        self.assertIsNone(parse_trend('{"trend":"","why":"x"}'))


if __name__ == "__main__":
    unittest.main()
