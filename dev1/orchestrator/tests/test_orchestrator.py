#!/usr/bin/env python3
"""Offline tests: mock department service, mock Grok, no network."""
from __future__ import annotations

import json
import os
import pathlib
import sys
import threading
import time
import unittest
import uuid
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import orchestrator as orch

ROOT = pathlib.Path(__file__).resolve().parents[1]


class FakeService:
    def __init__(self, pulse_status: int = 404, fail_depts: tuple[str, ...] = (), trend_task: str | None = None):
        self.events: list[dict] = []
        self.tasks: list[dict] = []
        self.pulse_calls: list[dict] = []
        self.pulse_status = pulse_status
        self.fail_depts = set(fail_depts)
        self.trend_task = trend_task

    def __call__(self, method: str, url: str, body: dict | None):
        parsed = urlparse(url)
        path = parsed.path
        if method == "GET" and path == "/health":
            return 200, {"ok": True, "service": "fake"}
        if method == "POST" and path == "/api/events":
            self.events.append(dict(body or {}))
            return 200, {"ok": True, "event": body}
        if method == "POST" and path == "/api/tasks":
            body = body or {}
            tid = "task-" + uuid.uuid4().hex[:6]
            rec = {"task_id": tid, "dept": body.get("for_dept"), "title": body.get("title"),
                   "parent_id": body.get("parent_id"), "status": "queued", "detail": body.get("detail"),
                   "meta": body.get("meta")}
            self.tasks.append(rec)
            base = {"dept": body.get("for_dept"), "task_id": tid, "summary": body.get("title"),
                    "mode": "mock", "parent_id": body.get("parent_id"), "actor": "auto",
                    "output": {"kind": "task"}}
            self.events.append({**base, "status": "queued"})
            if body.get("for_dept") in self.fail_depts:
                self.events.append({**base, "status": "failed", "summary": "dept failed"})
            return 200, {"ok": True, "task": rec}
        if method == "POST" and path == "/api/pulse/start":
            self.pulse_calls.append(dict(body or {}))
            if self.pulse_status >= 400:
                return self.pulse_status, {"ok": False, "error": "not found"}
            data = {"ok": True, "started": True}
            if self.trend_task:
                data["trend_task"] = self.trend_task
            return 200, data
        if method == "GET" and path == "/api/events":
            qs = parse_qs(parsed.query)
            evs = list(self.events)
            if qs.get("task_id"):
                evs = [e for e in evs if e.get("task_id") == qs["task_id"][0]]
            if qs.get("dept"):
                evs = [e for e in evs if e.get("dept") == qs["dept"][0]]
            limit = int((qs.get("limit") or ["200"])[0])
            return 200, {"events": evs[-limit:]}
        return 500, {"error": f"unhandled {method} {path}"}


def make_orch(fake: FakeService, **kw) -> orch.Orchestrator:
    client = orch.DeptClient(base="http://127.0.0.1:8810", transport=fake)
    return orch.Orchestrator(client=client, **kw)


class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        self._key = os.environ.pop("XAI_API_KEY", None)

    def tearDown(self):
        if self._key is not None:
            os.environ["XAI_API_KEY"] = self._key
        else:
            os.environ.pop("XAI_API_KEY", None)

    def test_mock_is_default_and_grok_is_not_called_without_a_key(self):
        self.assertEqual(orch.mode_from_env(), "mock")
        calls = [0]
        self.assertIsNone(orch.grok_plan("hello", 3, 3, calls))
        self.assertEqual(calls[0], 0)

    def test_general_request_routes_and_posts_orchestrator_events(self):
        fake = FakeService()
        out = make_orch(fake).submit("research the market and draft a sales lead note")
        depts = [t["dept"] for t in fake.tasks]
        self.assertIn("research", depts)
        self.assertIn("sales", depts)
        self.assertEqual(out["mode"], "mock")
        self.assertEqual(out["intent"], "general")
        orch_events = [e for e in fake.events if e.get("dept") == "orchestrator"]
        self.assertGreaterEqual(len(orch_events), 2)
        for ev in orch_events:
            self.assertEqual(ev["actor"], "dev1-orchestrator")
            self.assertEqual(ev["mode"], "mock")
            self.assertIn(ev["status"], orch.STATUSES)
            self.assertNotIn("@", json.dumps(ev))

    def test_pulse_kicks_research_only_and_tries_pulse_start(self):
        fake = FakeService(pulse_status=404)
        out = make_orch(fake).pulse("Launch something on what's trending today")
        self.assertEqual(out["intent"], "pulse")
        self.assertEqual([t["dept"] for t in fake.tasks], ["research"])
        self.assertEqual(len(fake.pulse_calls), 1)
        self.assertEqual(fake.pulse_calls[0].get("source"), "backup")
        self.assertNotIn("trend", fake.pulse_calls[0])
        self.assertEqual(out["pulse"]["pulse_start"], "unavailable")
        self.assertFalse(any(t["dept"] in orch.PULSE_CHAIN_DEPTS for t in fake.tasks))
        meta = fake.tasks[0]["meta"]
        self.assertEqual(meta.get("expect"), "trend_spotted")
        joined = " ".join(e.get("summary", "") for e in fake.events if e.get("dept") == "orchestrator")
        self.assertIn("Pulse", joined)

    def test_pulse_start_ok_still_does_not_route_the_chain(self):
        fake = FakeService(pulse_status=200)
        planner = lambda text, max_tasks: {
            "intent": "pulse", "summary": "pulse", "planner": "grok",
            "tasks": [
                {"dept": "design", "title": "logo", "detail": "nope", "needs_approval": False},
                {"dept": "research", "title": "Spot trend", "detail": "emit trend_spotted", "needs_approval": False},
                {"dept": "marketing", "title": "posts", "detail": "nope", "needs_approval": False},
                {"dept": "finance", "title": "margin", "detail": "nope", "needs_approval": False},
            ],
        }
        out = make_orch(fake, planner=planner).pulse("Launch something on what's trending today")
        self.assertEqual(out["pulse"]["pulse_start"], "ok")
        self.assertEqual([t["dept"] for t in fake.tasks], ["research"])

    def test_pulse_trend_task_kicks_trend_bot_without_blocking(self):
        fake = FakeService(pulse_status=200, trend_task="pulse-1")
        calls = []
        gate = threading.Event()

        def fake_run(hub):
            calls.append(hub)
            gate.wait(2)

        original = orch.run_trend_bot
        orch.run_trend_bot = fake_run
        os.environ.pop("ORCH_AUTO_RESEARCH", None)
        try:
            started = time.monotonic()
            out = make_orch(fake).pulse("Launch something on what's trending today")
            elapsed = time.monotonic() - started
            gate.set()
            deadline = time.monotonic() + 2
            while not calls and time.monotonic() < deadline:
                time.sleep(0.01)
        finally:
            gate.set()
            orch.run_trend_bot = original
        self.assertLess(elapsed, 1.0)
        self.assertEqual(calls, ["http://127.0.0.1:8810"])
        self.assertEqual(out["pulse"]["pulse_start"], "ok")
        self.assertEqual(fake.tasks[0]["meta"].get("trend_task"), "pulse-1")

        calls.clear()
        os.environ["ORCH_AUTO_RESEARCH"] = "0"
        orch.run_trend_bot = fake_run
        try:
            make_orch(FakeService(pulse_status=200, trend_task="pulse-2")).pulse(
                "Launch something on what's trending today")
            time.sleep(0.05)
        finally:
            orch.run_trend_bot = original
            os.environ.pop("ORCH_AUTO_RESEARCH", None)
        self.assertEqual(calls, [])

    def test_budget_cap(self):
        fake = FakeService()
        text = "research the market, write marketing content, email sales leads, answer a support ticket, and check finance margin"
        out = make_orch(fake, max_tasks=2).submit(text)
        self.assertLessEqual(len(fake.tasks), 2)
        self.assertEqual(out["budget"]["max_tasks"], 2)
        self.assertLessEqual(out["budget"]["tasks_routed"], 2)

    def test_needs_approval_does_not_block_other_tasks(self):
        fake = FakeService()
        out = make_orch(fake).submit("design a logo and review the contract")
        depts = {t["dept"] for t in fake.tasks}
        self.assertIn("design", depts)
        self.assertIn("legal", depts)
        legal = next(t for t in out["tasks"] if t["dept"] == "legal")
        self.assertTrue(legal["needs_approval"])
        self.assertTrue(any(e.get("status") == "needs_approval" for e in fake.events if e.get("dept") == "orchestrator"))
        self.assertEqual(len(fake.tasks), 2)

    def test_failed_task_retried_once(self):
        fake = FakeService(fail_depts=("sales",))
        o = make_orch(fake)
        out = o.submit("email sales leads about the drop")
        self.assertEqual(len(fake.tasks), 1)
        out = o.reconcile(out["request_id"])
        self.assertEqual(len([t for t in fake.tasks if t["dept"] == "sales"]), 2)
        retried = [t for t in out["tasks"] if t.get("retry_of")]
        self.assertEqual(len(retried), 1)
        again = o.reconcile(out["request_id"])
        self.assertEqual(len([t for t in fake.tasks if t["dept"] == "sales"]), 2)
        self.assertEqual(len([t for t in again["tasks"] if t.get("retry_of")]), 1)

    def test_chain_stalled_is_noted_not_duplicated(self):
        fake = FakeService()
        o = make_orch(fake)
        out = o.submit("research the market")
        fake.events.append({
            "dept": "integrations", "task_id": "stall-9", "status": "failed", "mode": "mock",
            "summary": "chain_stalled waiting on design", "actor": "dev3-integrations",
            "parent_id": out["request_id"], "output": {"kind": "chain_stalled"},
        })
        o.reconcile(out["request_id"])
        o.reconcile(out["request_id"])
        noted = [e for e in fake.events if (e.get("output") or {}).get("kind") == "stall_noted"]
        self.assertEqual(len(noted), 1)
        self.assertEqual(noted[0]["dept"], "orchestrator")
        stalled = [e for e in fake.events if (e.get("output") or {}).get("kind") == "chain_stalled"]
        self.assertEqual(len(stalled), 1)
        self.assertEqual(stalled[0]["dept"], "integrations")

    def test_secrets_and_emails_are_scrubbed(self):
        fake = FakeService()
        secret = "xai-" + ("a" * 24)
        make_orch(fake).submit(f"research this {secret} and mail ada@example.com")
        blob = json.dumps(fake.events)
        self.assertNotIn(secret, blob)
        self.assertNotIn("ada@example.com", blob)
        self.assertIn("[redacted]", blob)
        self.assertIn("[redacted-email]", blob)

    def test_grok_posts_only_to_xai(self):
        os.environ["XAI_API_KEY"] = "unit-test-key"
        os.environ["GROK_TEXT_MODEL"] = "grok-4"
        captured = {}

        def fake_http(method, url, body=None, timeout=10, headers=None):
            captured["method"] = method
            captured["url"] = url
            captured["body"] = body
            captured["headers"] = headers or {}
            plan = {"intent": "general", "summary": "ok", "tasks": [
                {"dept": "research", "title": "look", "detail": "market", "needs_approval": False}
            ]}
            return 200, {"choices": [{"message": {"content": json.dumps(plan)}}]}

        original = orch._http_json
        orch._http_json = fake_http
        try:
            plan = orch.grok_plan("check the market", 3, 3, [0])
        finally:
            orch._http_json = original
            os.environ.pop("GROK_TEXT_MODEL", None)
        self.assertEqual(plan["planner"], "grok")
        self.assertEqual(plan["model"], "grok-4")
        self.assertTrue(captured["url"].startswith("https://api.x.ai/v1/"))
        self.assertEqual(captured["body"]["model"], "grok-4")
        for banned in ("stop", "presence_penalty", "frequency_penalty"):
            self.assertNotIn(banned, captured["body"])
        self.assertTrue(captured["headers"].get("Authorization", "").startswith("Bearer "))

    def test_fast_model_env_used_when_text_model_unset(self):
        os.environ["XAI_API_KEY"] = "unit-test-key"
        os.environ.pop("GROK_TEXT_MODEL", None)
        os.environ["GROK_FAST_MODEL"] = "grok-4"
        captured = {}

        def fake_http(method, url, body=None, timeout=10, headers=None):
            captured["model"] = (body or {}).get("model")
            captured["url"] = url
            return 200, {"choices": [{"message": {"content": json.dumps({
                "intent": "general", "summary": "s", "tasks": []
            })}}]}

        original = orch._http_json
        orch._http_json = fake_http
        try:
            orch.grok_plan("hi", 2, 2, [0])
        finally:
            orch._http_json = original
            os.environ.pop("GROK_FAST_MODEL", None)
        self.assertEqual(captured["model"], "grok-4")
        self.assertTrue(captured["url"].startswith("https://api.x.ai/v1/"))

    def test_default_max_tasks_is_13(self):
        self.assertEqual(orch.DEFAULT_MAX_TASKS, 13)
        self.assertEqual(make_orch(FakeService()).max_tasks, 13)
        args = orch.build_parser().parse_args(["request", "hello"])
        self.assertEqual(args.max_tasks, 13)
        text = (
            "research the market, write marketing content, email sales leads, "
            "answer a support ticket, engineering should build the listing, "
            "check finance margin, review the contract, and design a logo"
        )
        fake = FakeService()
        out = make_orch(fake).submit(text)
        self.assertEqual(out["budget"]["max_tasks"], 13)
        self.assertGreater(len(fake.tasks), 6)

    def _pulse_planner(self):
        return lambda text, max_tasks: {
            "intent": "pulse", "summary": "pulse", "planner": "mock",
            "tasks": [{"dept": "research", "title": "Spot trend", "detail": "emit trend_spotted", "needs_approval": False}],
        }

    def test_pulse_passes_live_trend_when_key_set(self):
        os.environ["XAI_API_KEY"] = "unit-test-key"
        fake = FakeService(pulse_status=200)
        seen = {}

        def fake_lookup(query, timeout=45):
            seen["timeout"] = timeout
            seen["query"] = query
            return {"trend": "Pixel frogs", "why": "X wants frog stickers.", "source": "x", "mode": "live"}

        original = orch.lookup_live_trend
        orch.lookup_live_trend = fake_lookup
        try:
            out = make_orch(fake, planner=self._pulse_planner()).pulse("Launch something on what's trending today")
        finally:
            orch.lookup_live_trend = original
        body = fake.pulse_calls[0]
        self.assertEqual(seen["timeout"], orch.TREND_LOOKUP_TIMEOUT)
        self.assertLessEqual(seen["timeout"], 50)
        self.assertEqual(body["trend"], "Pixel frogs")
        self.assertEqual(body["why"], "X wants frog stickers.")
        self.assertEqual(body["source"], "x")
        self.assertEqual(body["mode"], "live")
        self.assertEqual(out["pulse"]["pulse_start"], "ok")

    def test_pulse_trend_failure_falls_back_to_backup(self):
        os.environ["XAI_API_KEY"] = "unit-test-key"
        fake = FakeService(pulse_status=200)

        def fake_lookup(query, timeout=45):
            raise TimeoutError("slow")

        original = orch.lookup_live_trend
        orch.lookup_live_trend = fake_lookup
        try:
            make_orch(fake, planner=self._pulse_planner()).pulse("Launch something on what's trending today")
        finally:
            orch.lookup_live_trend = original
        body = fake.pulse_calls[0]
        self.assertEqual(body.get("source"), "backup")
        self.assertNotIn("trend", body)

    def test_pulse_without_key_does_not_call_grok_trend(self):
        fake = FakeService(pulse_status=404)
        called = []
        original = orch.lookup_live_trend
        orch.lookup_live_trend = lambda *a, **k: called.append(1)
        try:
            make_orch(fake).pulse("Launch something on what's trending today")
        finally:
            orch.lookup_live_trend = original
        self.assertEqual(called, [])
        self.assertEqual(fake.pulse_calls[0].get("source"), "backup")
        self.assertNotIn("trend", fake.pulse_calls[0])

    def test_lookup_live_trend_parses_grok_and_ignores_failure(self):
        os.environ["XAI_API_KEY"] = "unit-test-key"
        os.environ["GROK_TEXT_MODEL"] = "grok-4"
        dev1 = str(ROOT.parent)
        if dev1 not in sys.path:
            sys.path.insert(0, dev1)
        import common.grok as grok_mod

        captured = {}

        class FakeClient:
            def __init__(self, settings, sender=None):
                self.settings = settings

            def respond(self, prompt, tools=None, fast=False, timeout=50):
                captured["tools"] = tools
                captured["timeout"] = timeout
                captured["prompt"] = prompt
                if captured.get("fail"):
                    raise grok_mod.GrokError("xAI responses HTTP 500")
                text = captured.get("text") or '{"trend":"Orbit cats","why":"They took over the timeline."}'
                return grok_mod.GrokResult(text, "live", "grok-4", False)

        original = grok_mod.GrokClient
        grok_mod.GrokClient = FakeClient
        try:
            found = orch.lookup_live_trend("frog stickers")
            self.assertEqual(found["trend"], "Orbit cats")
            self.assertEqual(found["why"], "They took over the timeline.")
            self.assertEqual(found["source"], "x")
            self.assertEqual(found["mode"], "live")
            self.assertEqual([t["type"] for t in captured["tools"]], ["x_search", "web_search"])
            self.assertLessEqual(captured["timeout"], 45)
            self.assertIn("x_search", captured["prompt"])
            captured["fail"] = True
            self.assertIsNone(orch.lookup_live_trend("again"))
            captured["fail"] = False
            captured["text"] = "not json"
            self.assertIsNone(orch.lookup_live_trend("again"))
        finally:
            grok_mod.GrokClient = original
            os.environ.pop("GROK_TEXT_MODEL", None)

    def test_grok_plan_logs_status_and_truncated_body_without_key(self):
        os.environ["XAI_API_KEY"] = "unit-test-key"
        secret = "unit-test-key"

        def fake_http(method, url, body=None, timeout=10, headers=None):
            self.assertTrue(url.startswith("https://api.x.ai/v1/"))
            return 429, {"error": "slow down " + secret + ("E" * 400)}

        original = orch._http_json
        orch._http_json = fake_http
        try:
            with self.assertLogs("orchestrator", level="WARNING") as cm:
                plan = orch.grok_plan("check the market", 3, 3, [0])
        finally:
            orch._http_json = original
        self.assertIsNone(plan)
        text = "\n".join(cm.output)
        self.assertIn("429", text)
        self.assertIn("slow down", text)
        self.assertNotIn(secret, text)
        self.assertNotIn("Bearer", text)
        self.assertNotIn("Authorization", text)
        self.assertNotIn("E" * 301, text)

    def test_grok_client_logs_http_error_without_key_or_headers(self):
        dev1 = str(ROOT.parent)
        if dev1 not in sys.path:
            sys.path.insert(0, dev1)
        from common.config import Settings
        from common.grok import GrokClient, GrokError

        secret = "super-secret-key"

        def sender(url, payload, key):
            self.assertEqual(url, "https://api.x.ai/v1/responses")
            return 503, {"error": "nope " + secret + ("Z" * 400)}

        settings = Settings(
            xai_api_key=secret,
            text_model="grok-4",
            fast_model="grok-4",
            image_model="grok-imagine-image-2.0",
            departments_base_url="http://127.0.0.1:8810",
        )
        with self.assertLogs("grok", level="WARNING") as cm:
            with self.assertRaises(GrokError):
                GrokClient(settings, sender=sender).respond("find a trend", tools=[{"type": "x_search"}])
        text = "\n".join(cm.output)
        self.assertIn("503", text)
        self.assertIn("nope", text)
        self.assertNotIn(secret, text)
        self.assertNotIn("authorization", text.lower())
        self.assertNotIn("Bearer", text)
        self.assertNotIn("Z" * 301, text)

    def test_heuristic_plan_matches_hr_and_data_as_words(self):
        text = (
            "Coordinate all departments: research a trend, draft marketing, sales outreach, "
            "support, engineering, ops, finance margin, legal review, HR, design, data and QA check"
        )
        plan = orch.heuristic_plan(text, 13)
        depts = [t["dept"] for t in plan["tasks"]]
        self.assertEqual(len(plan["tasks"]), 12)
        self.assertIn("hr", depts)
        self.assertIn("integrations", depts)
        three = orch.heuristic_plan("three throughput", 13)
        self.assertNotIn("hr", [t["dept"] for t in three["tasks"]])

    def test_sources_are_grok_only(self):
        """Fail if any orchestrator file names another provider or its API host."""
        needles = (
            "gp" + "t-",
            "cl" + "aude",
            "gem" + "ini",
            "anth" + "ropic",
            "api.open" + "ai.com",
        )
        allowed_suffixes = {".py", ".md", ".txt", ".toml"}
        bad = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in allowed_suffixes and path.name != "requirements.txt":
                continue
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            for needle in needles:
                if needle in text:
                    bad.append(f"{path.relative_to(ROOT)} contains {needle}")
        self.assertEqual(bad, [])
        src = (ROOT / "orchestrator.py").read_text(encoding="utf-8")
        self.assertIn("https://api.x.ai/v1", src)
        self.assertIn("XAI_API_KEY", src)
        self.assertIn("GROK_TEXT_MODEL", src)
        self.assertIn("GROK_FAST_MODEL", src)


if __name__ == "__main__":
    unittest.main()
