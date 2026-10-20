"""Offline tests: mocked Grok and a mocked department service. No network."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from marketing_bot.bot import MarketingBot, is_listing_live
from marketing_bot.clients import GrokClient, _BANNED_BODY_KEYS
from marketing_bot.drafts import mock_drafts, public_content
from marketing_bot import config


def listing(task="sale-1", **product):
    body = {"type": "sticker", "title": "Orbit Cat", "tagline": "Drawn from the timeline",
            "price": 12, "cost": 3, "trend": "orbit cats"}
    body.update(product)
    return {
        "dept": "design", "task_id": task, "status": "done", "actor": "dev2-bot",
        "summary": "listing live", "mode": "mock",
        "output": {
            "kind": "listing_live",
            "product": body,
            "url": "https://example.com/orbit-cat",
            "action": {"type": "listing_published", "url": "https://example.com/orbit-cat"},
        },
    }


class FakeEvents:
    def __init__(self, verdicts=None, fail_register=False):
        self.events = []
        self.qa_calls = []
        self.webhooks = []
        self.verdicts = list(verdicts or [{"verdict": "pass", "score": 1, "reasons": ["all checks passed"]}])
        self.fail_register = fail_register

    def post_event(self, ev):
        self.events.append(ev)
        return {"ok": True, "event": ev}

    def list_events(self, limit=100, dept=None, task_id=None):
        return {"events": []}

    def register_webhook(self, url, dept):
        if self.fail_register:
            raise RuntimeError("departments down")
        self.webhooks.append({"url": url, "dept": dept})
        return {"ok": True, "webhooks": self.webhooks}

    def qa_check(self, body):
        self.qa_calls.append(body)
        if self.verdicts:
            return self.verdicts.pop(0)
        return {"verdict": "pass", "score": 1, "reasons": ["all checks passed"]}


class FakeGrok:
    live = False

    def complete_json(self, system, user):
        raise AssertionError("mock mode must not call Grok")


class MarketingTests(unittest.TestCase):
    def _bot(self, events, drafter=None):
        return MarketingBot(events=events, grok=FakeGrok(), drafter=drafter)

    def test_mock_drafts_are_sandbox_and_public_safe(self):
        drafts = mock_drafts({"product": listing()["output"]["product"], "url": "https://example.com/x"},
                             {"trend": "orbit cats", "why": "the posts would not stop", "source": "x"})
        self.assertFalse(drafts["posted"])
        self.assertTrue(drafts["sandbox"])
        self.assertIn("MOCK", drafts["engine"])
        text = public_content(drafts)
        self.assertNotIn("$", text)
        self.assertNotIn("@", text)
        self.assertIn("Orbit Cat", text)
        self.assertGreaterEqual(len(drafts["x_thread"]), 2)
        self.assertEqual(len(drafts["landing"]["bullets"]), 3)

    def test_listing_posts_running_then_done_with_needs_qa(self):
        fake = FakeEvents()
        order = []

        def drafter(listing_view, trend, reasons):
            order.append([e["status"] for e in fake.events])
            self.assertIsNone(reasons)
            return mock_drafts(listing_view, trend)

        bot = self._bot(fake, drafter)
        result = bot.handle_event(listing())
        self.assertEqual(result["status"], "done")
        self.assertEqual(order[0][0], "running")
        statuses = [e["status"] for e in fake.events]
        self.assertEqual(statuses[0], "running")
        final = fake.events[-1]
        self.assertEqual(final["dept"], "marketing")
        self.assertEqual(final["actor"], "dev1-marketing")
        self.assertEqual(final["status"], "done")
        self.assertFalse(final["output"]["needs_qa"])
        self.assertEqual(final["output"]["kind"], "public_post")
        self.assertFalse(final["output"]["posted"])
        self.assertEqual(final["mode"], "mock")
        self.assertNotIn("ts", final)
        self.assertEqual(len(fake.qa_calls), 1)
        self.assertEqual(fake.qa_calls[0]["kind"], "public_post")

    def test_qa_fail_revises_once_then_passes(self):
        fake = FakeEvents([
            {"verdict": "fail", "score": 0.5, "reasons": ["policy: banned/placeholder text 'TODO'"]},
            {"verdict": "pass", "score": 1, "reasons": ["all checks passed"]},
        ])
        calls = []

        def drafter(listing_view, trend, reasons):
            calls.append(reasons)
            return mock_drafts(listing_view, trend)

        bot = self._bot(fake, drafter)
        result = bot.handle_event(listing("sale-2"))
        self.assertEqual(result["status"], "done")
        self.assertEqual(len(calls), 2)
        self.assertIsNone(calls[0])
        self.assertTrue(calls[1])
        self.assertEqual(len(fake.qa_calls), 2)
        self.assertIn("running", [e["status"] for e in fake.events])

    def test_founder_logs_needs_approval_without_a_revise(self):
        fake = FakeEvents([{"verdict": "founder", "score": 0.85, "reasons": ["policy: pricing/money wording"]}])
        calls = []

        def drafter(listing_view, trend, reasons):
            calls.append(reasons)
            return mock_drafts(listing_view, trend)

        bot = self._bot(fake, drafter)
        result = bot.handle_event(listing("sale-3"))
        self.assertEqual(result["status"], "needs_approval")
        self.assertEqual(len(calls), 1)
        final = fake.events[-1]
        self.assertEqual(final["status"], "needs_approval")
        self.assertTrue(final["needs_approval"])
        self.assertFalse(final["output"]["needs_qa"])

    def test_ignores_unrelated_and_is_idempotent(self):
        fake = FakeEvents()
        bot = self._bot(fake)
        self.assertIsNone(bot.handle_event({"dept": "research", "task_id": "r1", "output": {"kind": "trend_spotted", "trend": "x", "why": "y", "source": "x"}}))
        self.assertEqual(len(fake.events), 0)
        ev = listing("sale-4")
        self.assertIsNotNone(bot.handle_event(ev))
        n = len(fake.events)
        self.assertIsNone(bot.handle_event(ev))
        self.assertEqual(len(fake.events), n)

    def test_design_request_when_listing_has_no_assets(self):
        fake = FakeEvents()
        bot = self._bot(fake)
        bot.handle_event(listing("sale-5"))
        kinds = [e["output"].get("kind") for e in fake.events]
        self.assertIn("design_request", kinds)
        design = next(e for e in fake.events if e["output"]["kind"] == "design_request")
        self.assertEqual(design["output"]["brand"], "Pulse Studio")
        self.assertIn("brief", design["output"])
        self.assertEqual(design["dept"], "marketing")

    def test_skips_design_request_when_assets_exist(self):
        fake = FakeEvents()
        bot = self._bot(fake)
        ev = listing("sale-6")
        ev["output"]["assets"] = ["logo.svg"]
        bot.handle_event(ev)
        kinds = [e["output"].get("kind") for e in fake.events]
        self.assertNotIn("design_request", kinds)

    def test_design_listing_image_counts_as_asset(self):
        fake = FakeEvents()
        bot = self._bot(fake)
        ev = listing("product-1")
        ev["dept"] = "design"
        ev["output"]["image_url"] = "/files/published/product-1/a.svg"
        bot.handle_event(ev)
        kinds = [e["output"].get("kind") for e in fake.events]
        self.assertNotIn("design_request", kinds)

    def test_echoed_listing_launches_once_per_product(self):
        fake = FakeEvents()
        bot = self._bot(fake)
        design = listing("product-2")
        design["dept"] = "design"
        echo = {"dept": "engineering", "task_id": "englist_x", "status": "done", "actor": "engineering-bot",
                "summary": "Engineering recorded the live listing", "mode": "live",
                "output": {"kind": "listing_live", "url": "/x", "price": 6, "listing_task": "product-2"}}
        self.assertIsNotNone(bot.handle_event(design))
        self.assertIsNone(bot.handle_event(echo))
        self.assertEqual(len(fake.qa_calls), 1)
        self.assertTrue(all(e["task_id"].startswith("mkt-product-2") for e in fake.events))

    def test_listing_live_launches_only_from_design(self):
        fake = FakeEvents()
        bot = self._bot(fake)
        sales = listing("sale-echo")
        sales["dept"] = "sales"
        engineering = listing("eng-echo")
        engineering["dept"] = "engineering"
        self.assertIsNone(bot.handle_event(sales))
        self.assertIsNone(bot.handle_event(engineering))
        self.assertEqual(fake.events, [])
        design = listing("product-9")
        design["dept"] = "design"
        self.assertIsNotNone(bot.handle_event(design))
        self.assertEqual(len(fake.qa_calls), 1)
        self.assertIsNone(bot.handle_event(design))
        self.assertEqual(len(fake.qa_calls), 1)

    def test_trend_spotted_is_passed_to_the_drafter(self):
        fake = FakeEvents()
        seen = {}

        def drafter(listing_view, trend, reasons):
            seen["trend"] = trend
            return mock_drafts(listing_view, trend)

        bot = self._bot(fake, drafter)
        bot.handle_event({
            "dept": "research", "task_id": "tr-1", "status": "done",
            "output": {"kind": "trend_spotted", "trend": "orbit cats", "why": "fan art took off", "source": "x"},
        })
        bot.handle_event(listing("sale-7"))
        self.assertEqual(seen["trend"]["why"], "fan art took off")
        self.assertEqual(seen["trend"]["source"], "x")

    def test_poll_picks_up_listing_live(self):
        fake = FakeEvents()
        ev = listing("sale-8")
        fake.list_events = lambda **k: {"events": [ev]}
        bot = self._bot(fake)
        handled = bot.poll_once()
        self.assertEqual(len(handled), 1)
        self.assertTrue(any(e["dept"] == "marketing" and e["status"] == "running" for e in fake.events))

    def test_webhook_register_uses_marketing_url_and_survives_failure(self):
        fake = FakeEvents()
        bot = self._bot(fake)
        res = bot.register_webhook()
        self.assertTrue(res["ok"])
        self.assertEqual(fake.webhooks, [{"url": "http://127.0.0.1:8899/pulse", "dept": "marketing"}])
        down = FakeEvents(fail_register=True)
        bot2 = self._bot(down)
        self.assertIsNone(bot2.register_webhook())

    def test_departments_url_default(self):
        self.assertTrue(config.DEPARTMENTS_URL.startswith("http://127.0.0.1:8810") or os.environ.get("DEPARTMENTS_URL"))
        self.assertEqual(config.WEBHOOK_URL, os.environ.get("MARKETING_WEBHOOK_URL", "http://127.0.0.1:8899/pulse"))

    def test_is_listing_live_accepts_action_kind(self):
        ev = {"output": {"action": {"kind": "listing_live", "product": {"title": "T"}}}}
        self.assertTrue(is_listing_live(ev))
        self.assertFalse(is_listing_live({"output": {"kind": "trend_spotted"}}))


class GrokClientTests(unittest.TestCase):
    def test_request_omits_reasoning_rejected_params(self):
        captured = {}

        def transport(method, url, body=None, headers=None, timeout=15):
            captured["body"] = body
            captured["url"] = url
            captured["headers"] = headers
            return {"choices": [{"message": {"content": "{\"x_post\":\"hi\"}"}}]}

        client = GrokClient(api_key="xai-test-key-not-real", model="grok-4", transport=transport)
        client.complete_json("sys", "user")
        for key in _BANNED_BODY_KEYS:
            self.assertNotIn(key, captured["body"])
        self.assertEqual(captured["body"]["model"], "grok-4")
        self.assertEqual(captured["url"], "https://api.x.ai/v1/chat/completions")
        self.assertNotIn("stop", json.dumps(captured["body"]))
        with self.assertRaises(ValueError):
            GrokClient(api_key="x", model="grok-4", base_url="https://example.invalid/v1")
        with self.assertRaises(ValueError):
            GrokClient(api_key="x", model="not-grok")

    def test_mock_when_no_key(self):
        client = GrokClient(api_key="", transport=lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
        self.assertFalse(client.live)
        with self.assertRaises(RuntimeError):
            client.complete_json("s", "u")


if __name__ == "__main__":
    unittest.main()
