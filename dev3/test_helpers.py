"""Tests for dev3/grok.py, dev3/qa_bridge.py, dev3/rehearse.py. No network: HTTP is mocked.
Run: python -m unittest dev3/test_helpers.py
"""
import io, json, os, sys, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "departments", "lib"))
import grok, qa_bridge, rehearse  # noqa: E402
try:
    import events as hub_events  # departments/lib/events.py from main
except Exception:
    hub_events = None


class Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def fake_urlopen(payload, calls=None):
    def f(req, timeout=None):
        if calls is not None:
            calls.append(req)
        return Resp(json.dumps(payload).encode())
    return f


MARGIN_LOW = {"kind": "margin_update", "ok": True, "revenue": 20.0, "cogs": 15.0, "payment_fees": 0.88,
              "margin": 4.12, "margin_pct": 20.6, "margin_frac": 0.206, "floor_pct": 25.0, "under_floor": True}
MARGIN_OK = dict(MARGIN_LOW, margin=26.25, margin_pct=52.5, margin_frac=0.525, revenue=50.0, under_floor=False)
FLAG = {"kind": "legal_review", "verdict": "flag", "issues": ["trademark: 'pokemon' is a protected mark"],
        "checked": "t1", "checked_kind": "trend_spotted"}
PASS = {"kind": "legal_review", "verdict": "pass", "issues": [], "checked": "t2", "checked_kind": "product_created"}


class GrokTests(unittest.TestCase):
    def test_no_key_is_mock_and_no_http(self):
        with mock.patch.dict(os.environ, {"XAI_API_KEY": ""}), mock.patch("urllib.request.urlopen") as u:
            r = grok.legal_opinion(FLAG); s = grok.margin_summary(MARGIN_LOW)
        u.assert_not_called()
        self.assertEqual((r["mode"], r["verdict"]), ("mock", "flag"))
        self.assertEqual(s["mode"], "mock"); self.assertIn("under floor", s["summary"])

    def test_live_parses_output_and_sends_bearer(self):
        calls = []
        body = {"output": [{"type": "reasoning"}, {"type": "message", "content": [{"type": "output_text", "text": "FLAG uses Pokemon mark"}]}]}
        with mock.patch.dict(os.environ, {"XAI_API_KEY": "test-key-123"}), \
             mock.patch("urllib.request.urlopen", fake_urlopen(body, calls)):
            r = grok.legal_opinion({"summary": "Pokemon cats", "output": {"trend": "Pokemon cats"}})
        self.assertEqual((r["mode"], r["verdict"]), ("live", "flag"))
        req = calls[0]
        self.assertEqual(req.full_url, grok.XAI_URL)
        self.assertEqual(req.get_header("Authorization"), "Bearer test-key-123")
        sent = json.loads(req.data)
        self.assertEqual(sent["model"], grok.XAI_MODEL); self.assertIn("input", sent)
        self.assertNotIn("test-key-123", json.dumps(r))

    def test_live_failure_falls_back_without_raising_or_leaking(self):
        def boom(req, timeout=None): raise TimeoutError("slow")
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"XAI_API_KEY": "secret-key-xyz"}), \
             mock.patch("urllib.request.urlopen", boom), mock.patch("sys.stderr", err):
            s = grok.margin_summary(MARGIN_OK)
        self.assertEqual(s["mode"], "mock"); self.assertIn("TimeoutError", s["engine"])
        self.assertNotIn("secret-key-xyz", err.getvalue() + json.dumps(s))

    def test_base_url_env_routes_to_proxy(self):
        import importlib
        try:
            with mock.patch.dict(os.environ, {"XAI_BASE_URL": "http://127.0.0.1:9999/v1/", "XAI_URL": ""}):
                importlib.reload(grok)
                self.assertEqual(grok.XAI_URL, "http://127.0.0.1:9999/v1/responses")
                calls = []
                body = {"output_text": "PASS fine"}
                with mock.patch.dict(os.environ, {"XAI_API_KEY": "k"}), mock.patch("urllib.request.urlopen", fake_urlopen(body, calls)):
                    grok.legal_opinion({"summary": "Tiny hat frogs"})
                self.assertEqual(calls[0].full_url, "http://127.0.0.1:9999/v1/responses")
            with mock.patch.dict(os.environ, {"XAI_BASE_URL": "", "XAI_URL": ""}):
                importlib.reload(grok)
                self.assertEqual(grok.XAI_URL, "https://api.x.ai/v1/responses")
        finally:
            importlib.reload(grok)

    def test_missing_margin_never_calls_grok(self):
        with mock.patch.dict(os.environ, {"XAI_API_KEY": "k"}), mock.patch("urllib.request.urlopen") as u:
            s = grok.margin_summary({"ok": False, "missing": ["pod_cost"]})
        u.assert_not_called(); self.assertIn("pod_cost", s["summary"])


class QABridgeTests(unittest.TestCase):
    def _run(self, fn, *a):
        calls = []
        with mock.patch("urllib.request.urlopen", fake_urlopen({"verdict": "founder", "score": 1.0, "reasons": []}, calls)):
            r = fn(*a)
        return r, calls

    def test_margin_under_floor_is_pricing(self):
        r, calls = self._run(qa_bridge.margin_check, "fin-o1", MARGIN_LOW, "http://hub:1")
        self.assertEqual(r["verdict"], "founder")
        self.assertEqual(calls[0].full_url, "http://hub:1/api/qa/check")
        b = json.loads(calls[0].data)
        self.assertEqual((b["dept"], b["task_id"], b["kind"]), ("finance", "fin-o1", "pricing"))
        self.assertTrue(set(b) <= {"dept", "task_id", "kind", "content", "context", "mode"})
        self.assertIsInstance(b["content"], str)

    def test_margin_ok_skips_qa(self):
        with mock.patch("urllib.request.urlopen") as u:
            self.assertIsNone(qa_bridge.margin_check("fin-o2", MARGIN_OK))
        u.assert_not_called()

    def test_legal_flag_is_kind_legal_and_pass_skips_qa(self):
        r, calls = self._run(qa_bridge.legal_check, "legal-x", FLAG, "http://hub:1")
        b = json.loads(calls[0].data)
        self.assertEqual((b["dept"], b["kind"]), ("legal", "legal")); self.assertIn("FLAG", b["content"])
        with mock.patch("urllib.request.urlopen") as u:
            self.assertIsNone(qa_bridge.legal_check("legal-y", PASS, "http://hub:1"))
        u.assert_not_called()

    def test_hub_down_returns_unavailable(self):
        def down(req, timeout=None): raise ConnectionRefusedError("nope")
        with mock.patch("urllib.request.urlopen", down):
            r = qa_bridge.legal_check("legal-y", FLAG, "http://127.0.0.1:9")
        self.assertEqual(r["verdict"], "unavailable")


class RehearseTests(unittest.TestCase):
    def test_chain_shape(self):
        c = rehearse.build_chain("abc")
        self.assertEqual([e["output"]["kind"] for e in c],
                         ["trend_spotted", "product_created", "listing_live", "order_placed", "order_placed"])
        self.assertEqual(c[2]["output"]["price"], 49)
        self.assertEqual((c[3]["output"]["unit_cost_usd"], c[3]["output"]["cost_usd"]), (14, 28))  # hub: cost_usd = order total
        self.assertNotIn("cost_usd", c[4]["output"])
        for e in c:
            self.assertFalse(e["actor"].startswith("dev3-"))  # agent.py skips its own dev3-* events
            self.assertTrue(set(e) <= {"ts", "dept", "task_id", "status", "summary", "mode", "parent_id", "actor", "output", "needs_approval"})

    @unittest.skipIf(hub_events is None, "departments/lib/events.py not importable")
    def test_every_event_passes_hub_validation(self):
        for e in rehearse.build_chain("val"):
            hub_events.validate(e)

    def test_main_posts_all(self):
        calls = []
        with mock.patch("urllib.request.urlopen", fake_urlopen({"ok": True}, calls)), mock.patch("sys.stdout", io.StringIO()):
            rc = rehearse.main(["--hub", "http://hub:1", "--mode", "synthetic"])
        self.assertEqual(rc, 0); self.assertEqual(len(calls), 5)
        self.assertTrue(all(c.full_url == "http://hub:1/api/events" for c in calls))

    def test_pulse_mode_starts_waits_and_orders(self):
        seq = []
        def fake(req, timeout=None):
            seq.append((req.get_method(), req.full_url.split("hub:1")[1]))
            path = seq[-1][1]
            if path == "/api/pulse/start": out = {"ok": True, "trend_task": "pulse-1"}
            elif path.startswith("/api/events"):
                out = {"events": [] if len([s for s in seq if s[1].startswith("/api/events")]) < 2 else [
                    {"task_id": "design-1", "parent_id": "pulse-1", "dept": "design", "status": "done", "output": {"kind": "product_created"}},
                    {"task_id": "design-1", "dept": "design", "status": "done", "output": {"kind": "listing_live"}}]}
            elif path == "/api/ops/order":
                self.assertEqual(json.loads(req.data)["task_id"], "design-1")
                out = {"ok": True, "order": {"order_id": "order-1", "qty": 2}}
            return Resp(json.dumps(out).encode())
        with mock.patch("urllib.request.urlopen", fake):
            rep = rehearse.pulse("http://hub:1", sleep=lambda s: None)
        self.assertEqual((rep["trend_task"], rep["listing_task"]), ("pulse-1", "design-1"))
        self.assertEqual(rep["order"]["order"]["order_id"], "order-1")
        self.assertEqual(seq[0], ("POST", "/api/pulse/start")); self.assertEqual(seq[-1], ("POST", "/api/ops/order"))


if __name__ == "__main__":
    unittest.main()
