"""Offline Trend bot tests. No network and no XAI key."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone

from common.config import Settings
from common.events import EventError
from common.grok import GrokError
from trend_bot.bot import find_recent_trend, load_backup, main, parse_trend, spot


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


def _iso(when):
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class Bus:
    def __init__(self, recent=None, fail_get=False):
        self.posts = []
        self.recent = list(recent or [])
        self.fail_get = fail_get
        self.got = None

    def get_events(self, **kwargs):
        self.got = kwargs
        if self.fail_get:
            raise EventError("unreachable")
        return {"events": self.recent}

    def post_event(self, **body):
        self.posts.append(body)
        return {"ok": True, "event": {**body, "ts": "server-set"}}


class TrendTests(unittest.TestCase):
    def _run(self, settings, grok_sender=None, recent=None, fail_get=False, force=False):
        from common.grok import GrokClient

        bus = Bus(recent, fail_get=fail_get)
        self.bus = bus
        result = spot(
            settings=settings,
            grok=GrokClient(settings, sender=grok_sender),
            events=bus,
            force=force,
        )
        return result, (bus.posts[0] if bus.posts else None)

    def _assert_accepted(self, spotted, mode):
        accepted = self.bus.posts[1]
        self.assertEqual(len(self.bus.posts), 2)
        self.assertEqual(accepted["dept"], "research")
        self.assertEqual(accepted["status"], "done")
        self.assertEqual(accepted["mode"], mode)
        self.assertEqual(accepted["actor"], "dev1-trend")
        self.assertEqual(accepted["task_id"], spotted["task_id"])
        self.assertEqual(accepted["parent_id"], spotted["task_id"])
        self.assertEqual(
            accepted["output"],
            {"kind": "trend_accepted", "trend": spotted["output"]["trend"], "source": "x"},
        )
        self.assertNotIn("STAND-IN", accepted["summary"])
        self.assertNotIn("standin", accepted["output"])
        self.assertTrue(accepted["summary"].startswith("Research: trend accepted"))

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
        self._assert_accepted(body, "mock")
        self.assertEqual(self.bus.got["dept"], "research")

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
        self._assert_accepted(body, "live")

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

    def test_same_trend_recent_skips_without_posting(self):
        backup, _why = load_backup()
        recent = [{
            "dept": "research",
            "task_id": "trend-already",
            "ts": _iso(datetime.now(timezone.utc) - timedelta(minutes=5)),
            "output": {"kind": "trend_spotted", "trend": "  " + backup.upper() + "  ", "source": "x"},
        }]
        result, body = self._run(_settings(), recent=recent)
        self.assertTrue(result["skipped"])
        self.assertIsNone(body)
        self.assertEqual(self.bus.posts, [])
        self.assertIn("Nothing posted", result["message"])
        self.assertIn("trend-already", result["message"])

    def test_force_and_unreachable_and_stale_still_post(self):
        backup, _why = load_backup()
        recent = [{
            "task_id": "trend-already",
            "ts": _iso(datetime.now(timezone.utc) - timedelta(minutes=5)),
            "output": {"kind": "trend_spotted", "trend": backup, "source": "x"},
        }]
        result, body = self._run(_settings(), recent=recent, force=True)
        self.assertFalse(result["skipped"])
        self.assertEqual(body["output"]["kind"], "trend_spotted")
        self.assertEqual(len(self.bus.posts), 2)
        self.assertIsNone(self.bus.got)

        stale = [{
            "task_id": "trend-old",
            "ts": _iso(datetime.now(timezone.utc) - timedelta(minutes=31)),
            "output": {"kind": "trend_spotted", "trend": backup, "source": "x"},
        }]
        _result, body = self._run(_settings(), recent=stale)
        self.assertEqual(body["output"]["trend"], backup)
        self.assertEqual(len(self.bus.posts), 2)

        _result, body = self._run(_settings(), recent=recent, fail_get=True)
        self.assertEqual(body["output"]["kind"], "trend_spotted")
        self.assertEqual(self.bus.posts[1]["output"]["kind"], "trend_accepted")

    def test_find_recent_ignores_other_kinds_and_old_rows(self):
        now = datetime.now(timezone.utc)
        rows = [
            {"ts": _iso(now - timedelta(hours=2)), "output": {"kind": "trend_spotted", "trend": "Frogs"}},
            {"ts": _iso(now), "output": {"kind": "trend_accepted", "trend": "Frogs"}},
        ]
        self.assertIsNone(find_recent_trend(rows, "frogs", now=now))
        rows.append({"task_id": "t-1", "output": {"kind": "trend_spotted", "trend": "Frogs"}})
        self.assertEqual(find_recent_trend(rows, " frogs ", now=now)["task_id"], "t-1")

    def test_main_skip_exits_zero(self):
        from io import StringIO
        from contextlib import redirect_stdout
        from unittest.mock import patch

        buf = StringIO()
        with patch("trend_bot.bot.spot", return_value={"skipped": True, "message": "skip: already posted. Nothing posted."}):
            with redirect_stdout(buf):
                code = main(["--force"])
        self.assertEqual(code, 0)
        self.assertIn("Nothing posted", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
