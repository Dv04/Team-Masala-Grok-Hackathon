"""Offline Trend bot tests. No network and no XAI key."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone

from common.config import Settings
from common.events import EventError
from common.grok import GrokError
from trend_bot.bot import find_recent_trend, find_trend, load_backup, main, parse_trend, serve, spot


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

    def test_main_serve_does_not_run_one_shot(self):
        from unittest.mock import patch

        with patch("trend_bot.bot.serve") as serve_mock, patch("trend_bot.bot.spot") as spot_mock:
            code = main(["--serve"])
        self.assertEqual(code, 0)
        serve_mock.assert_called_once_with()
        spot_mock.assert_not_called()


def _routed(task_id, title="Research the market", text="desk plants"):
    return {
        "task_id": task_id,
        "dept": "research",
        "status": "queued",
        "title": title,
        "detail": {"text": text, "kind": "routed_task", "source": "orchestrator"},
    }


class TaskBus(Bus):
    def __init__(self, tasks=None, recent=None, fail_tasks=False):
        super().__init__(recent=recent)
        self.tasks = list(tasks or [])
        self.fail_tasks = fail_tasks
        self.task_calls = []

    def get_tasks(self, **kwargs):
        self.task_calls.append(kwargs)
        if self.fail_tasks:
            raise EventError("tasks down")
        return list(self.tasks)


class FindTrendTests(unittest.TestCase):
    def test_no_key_returns_fixture_and_posts_nothing(self):
        from common.grok import GrokClient

        def grok_sender(url, payload, key):
            raise AssertionError("no key means no HTTP")

        trend, why = load_backup()
        found = find_trend(settings=_settings(), grok=GrokClient(_settings(), sender=grok_sender))
        self.assertEqual(found, {"trend": trend, "why": why, "source": "x", "mode": "mock"})

    def test_live_parse(self):
        from common.grok import GrokClient

        def grok_sender(url, payload, key):
            self.assertIn("x_search", [t["type"] for t in payload["tools"]])
            self.assertIn("desk plants", payload["input"])
            return 200, {"output_text": '{"trend":"Desk plants","why":"X wants plant stickers."}'}

        found = find_trend(
            "desk plants",
            settings=_settings(xai_api_key="test-key"),
            grok=GrokClient(_settings(xai_api_key="test-key"), sender=grok_sender),
        )
        self.assertEqual(found["mode"], "live")
        self.assertEqual(found["trend"], "Desk plants")
        self.assertEqual(found["source"], "x")

    def test_grok_failure_falls_back(self):
        from common.grok import GrokClient

        def grok_sender(url, payload, key):
            raise GrokError("xAI responses HTTP 500")

        found = find_trend(
            settings=_settings(xai_api_key="test-key"),
            grok=GrokClient(_settings(xai_api_key="test-key"), sender=grok_sender),
        )
        self.assertEqual(found["mode"], "mock")
        self.assertEqual(found["trend"], load_backup()[0])
        self.assertEqual(found["source"], "x")


class ServeTests(unittest.TestCase):
    def _serve(self, bus, settings=None, grok_sender=None, **kwargs):
        from common.grok import GrokClient

        settings = settings or _settings()
        serve(
            poll_sec=kwargs.pop("poll_sec", 2),
            settings=settings,
            grok=GrokClient(settings, sender=grok_sender),
            events=bus,
            **kwargs,
        )
        return bus

    def test_posts_research_task_done_for_non_pulse_task(self):
        bus = TaskBus(tasks=[_routed("research-9", text="what is trending for stickers")])
        self._serve(bus, once=True)
        self.assertEqual(bus.task_calls, [{"dept": "research", "status": "queued"}])
        self.assertEqual(len(bus.posts), 1)
        posted = bus.posts[0]
        trend, why = load_backup()
        self.assertEqual(posted["dept"], "research")
        self.assertEqual(posted["parent_id"], "research-9")
        self.assertNotEqual(posted["task_id"], "research-9")
        self.assertTrue(posted["task_id"])
        self.assertEqual(posted["status"], "done")
        self.assertEqual(posted["actor"], "dev1-trend")
        self.assertEqual(posted["mode"], "mock")
        self.assertEqual(posted["output"]["kind"], "research_task_done")
        self.assertEqual(posted["output"]["trend"], trend)
        self.assertEqual(posted["output"]["why"], why)
        self.assertEqual(posted["output"]["source"], "x")
        self.assertEqual(posted["output"]["summary"], posted["summary"])
        self.assertIn(trend, posted["summary"])

    def test_live_mode_and_query_come_from_the_task(self):
        seen = {}

        def grok_sender(url, payload, key):
            seen["input"] = payload["input"]
            return 200, {"output_text": '{"trend":"Desk plants","why":"X is posting plant corners."}'}

        bus = TaskBus(tasks=[_routed("research-2", title="Research desk plants", text="plant corners")])
        self._serve(bus, settings=_settings(xai_api_key="test-key"), grok_sender=grok_sender, once=True)
        self.assertIn("desk plants", seen["input"].lower())
        self.assertEqual(bus.posts[0]["mode"], "live")
        self.assertEqual(bus.posts[0]["output"]["trend"], "Desk plants")
        self.assertEqual(bus.posts[0]["output"]["source"], "x")

    def test_skips_pulse_and_other_depts(self):
        bus = TaskBus(tasks=[
            {"task_id": "research-p", "dept": "research", "status": "queued",
             "detail": {"expect": "trend_spotted", "trend_task": "pulse-1", "kind": "pulse_kickoff"}},
            {"task_id": "research-q", "dept": "research", "status": "queued",
             "detail": {"expect": "trend_spotted", "kind": "pulse_kickoff"}},
            {"task_id": "sales-1", "dept": "sales", "status": "queued", "detail": {"kind": "routed_task"}},
            _routed("research-ok"),
        ])
        self._serve(bus, once=True)
        self.assertEqual([p["parent_id"] for p in bus.posts], ["research-ok"])

    def test_dedupes_by_task_id_across_polls(self):
        sleeps = []
        bus = TaskBus(tasks=[_routed("research-9")])
        self._serve(bus, stop_after=2, sleep=lambda n: sleeps.append(n))
        self.assertEqual(len(bus.posts), 1)
        self.assertEqual(sleeps, [2])

    def test_skips_task_already_answered(self):
        done = [{
            "dept": "research",
            "task_id": "answer-old",
            "parent_id": "research-9",
            "status": "done",
            "output": {"kind": "research_task_done", "summary": "s", "trend": "t", "why": "w", "source": "x"},
        }]
        bus = TaskBus(tasks=[_routed("research-9")], recent=done)
        self._serve(bus, once=True)
        self.assertEqual(bus.posts, [])

    def test_event_inbox_when_tasks_endpoint_fails(self):
        class EventsOnly(Bus):
            def get_tasks(self, **kwargs):
                raise EventError("no inbox")

            def get_events(self, **kwargs):
                return {"events": [{
                    "dept": "research",
                    "task_id": "research-e",
                    "status": "queued",
                    "output": {
                        "kind": "task",
                        "title": "Market",
                        "detail": {"kind": "routed_task", "text": "competitors"},
                    },
                }]}

        bus = EventsOnly()
        self._serve(bus, once=True)
        self.assertEqual(len(bus.posts), 1)
        self.assertEqual(bus.posts[0]["parent_id"], "research-e")
        self.assertEqual(bus.posts[0]["output"]["kind"], "research_task_done")

    def test_errors_do_not_stop_the_loop(self):
        class Flaky(TaskBus):
            def post_event(self, **body):
                if body.get("parent_id") == "a":
                    raise EventError("post failed")
                return super().post_event(**body)

        bus = Flaky(tasks=[_routed("a"), _routed("b")])
        self._serve(bus, once=True)
        self.assertEqual([p["parent_id"] for p in bus.posts], ["b"])

        class BothDown(Bus):
            def get_tasks(self, **kwargs):
                raise RuntimeError("tasks down")

            def get_events(self, **kwargs):
                raise RuntimeError("events down")

        down = BothDown()
        self._serve(down, once=True)
        self.assertEqual(down.posts, [])


if __name__ == "__main__":
    unittest.main()


class ClaimTests(unittest.TestCase):
    def test_accepts_pulse_trend_on_routed_task_instead_of_new_chain(self):
        from common.grok import GrokClient

        class TaskBus(Bus):
            def get_tasks(self, **kw):
                return [{"task_id": "research-1", "parent_id": "req-1", "status": "queued",
                         "detail": {"expect": "trend_spotted", "trend_task": "pulse-1"}}]

            def get_events(self, **kw):
                return {"events": [{"task_id": "pulse-1", "output": {"kind": "trend_spotted", "trend": "Austin heat", "source": "backup"}}]}

        bus = TaskBus()
        s = _settings()
        r = spot(settings=s, grok=GrokClient(s), events=bus)
        self.assertTrue(r["skipped"])
        self.assertEqual(len(bus.posts), 1)
        p = bus.posts[0]
        self.assertEqual((p["task_id"], p["parent_id"], p["output"]["kind"]), ("research-1", "req-1", "trend_accepted"))
        self.assertEqual(p["output"]["trend_task"], "pulse-1")
        self.assertEqual(p["mode"], "mock")

    def test_pulse_accept_uses_the_trend_mode(self):
        from common.grok import GrokClient

        class TaskBus(Bus):
            def get_tasks(self, **kw):
                return [{"task_id": "research-1", "parent_id": "req-1", "status": "queued",
                         "detail": {"expect": "trend_spotted", "trend_task": "pulse-1"}}]

            def get_events(self, **kw):
                return {"events": [{
                    "task_id": "pulse-1",
                    "mode": "live",
                    "output": {"kind": "trend_spotted", "trend": "Austin heat", "source": "x"},
                }]}

        bus = TaskBus()
        s = _settings()
        spot(settings=s, grok=GrokClient(s), events=bus)
        self.assertEqual(bus.posts[0]["mode"], "live")
        self.assertEqual(bus.posts[0]["output"]["source"], "x")
