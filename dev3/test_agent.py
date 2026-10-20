"""Unit tests for dev3 depts (no hub needed): python -m unittest dev3/test_agent.py"""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["DEV3_SEEN"] = os.path.join(tempfile.mkdtemp(), "seen.json")
os.environ["XAI_API_KEY"] = ""          # unit tests never call xAI
os.environ["HUB"] = "http://127.0.0.1:9"  # and never reach a real hub
from unittest import mock  # noqa: E402
import agent  # noqa: E402


def ev(task_id, k, dept="ops", parent=None, ts="2026-10-20T00:00:00Z", **out):
    e = {"task_id": task_id, "dept": dept, "status": "done", "summary": out.pop("summary", k), "ts": ts,
         "actor": f"{dept}-bot", "mode": "mock", "output": {"kind": k, **out}}
    if parent:
        e["parent_id"] = parent
    return e


class Finance(unittest.TestCase):
    def test_margin_math(self):
        o = agent.finance_margin(ev("o1", "order_placed", price=25, pod_cost=11, qty=2))
        self.assertTrue(o["ok"])
        self.assertEqual(o["revenue"], 50.0)
        self.assertEqual(o["payment_fees"], 1.75)  # 50*0.029 + 0.30
        self.assertEqual(o["margin"], 26.25)
        self.assertFalse(o["under_floor"])

    def test_price_from_parent_listing(self):
        lst = ev("l1", "listing_live", dept="sales", product={"price_usd": 24, "cost_usd": 9})
        order = ev("o4", "order_placed", parent="l1", qty=1)
        o = agent.finance_margin(order, {"l1": lst, "o4": order})
        self.assertTrue(o["ok"])
        self.assertEqual(o["margin"], 14.0)  # 24 - 9 - (0.70 + 0.30)

    def test_under_floor(self):
        self.assertTrue(agent.finance_margin(ev("o2", "order_placed", price=12, pod_cost=10))["under_floor"])

    def test_hub_order_total_cost_not_double_counted(self):
        # real hub shape: order_placed carries order totals; listing_live (parent) carries unit product price/cost
        lst = ev("p1", "listing_live", dept="design", product={"price_usd": 6.0, "cost_usd": 1.6})
        order = ev("o5", "order_placed", dept="ops", parent="p1", qty=2, revenue_usd=12.0, cost_usd=3.2)
        o = agent.finance_margin(order, {"p1": lst, "o5": order})
        self.assertEqual((o["revenue"], o["cogs"], o["payment_fees"], o["margin"]), (12.0, 3.2, 0.65, 8.15))
        self.assertEqual((o["margin_pct"], round(o["margin_frac"], 2)), (67.9, 0.68))
        # no parent: order-total cost_usd is used as the total, not multiplied
        o = agent.finance_margin(ev("o6", "order_placed", qty=2, price_usd=6.0, cost_usd=3.2))
        self.assertEqual(o["cogs"], 3.2)
        # explicit unit cost wins
        o = agent.finance_margin(ev("o7", "order_placed", qty=2, price_usd=6.0, unit_cost_usd=1.6, cost_usd=3.2))
        self.assertEqual(o["cogs"], 3.2)

    def test_missing_cost_is_not_guessed(self):
        o = agent.finance_margin(ev("o3", "order_placed", price=20))
        self.assertFalse(o["ok"])
        self.assertEqual(o["missing"], ["pod_cost"])


class Legal(unittest.TestCase):
    def test_pass(self):
        self.assertEqual(agent.legal_review(ev("t1", "trend_spotted", trend="cats doing taxes"))["verdict"], "pass")

    def test_trademark_and_person(self):
        r = agent.legal_review(ev("t2", "product_created", title="Elon Musk x Nike tee"))
        self.assertEqual(r["verdict"], "flag")
        self.assertEqual(len(r["issues"]), 2)

    def test_no_substring_false_positive(self):
        # "pineapple" contains "apple"; "snfl" style substrings must not match
        self.assertEqual(agent.legal_review(ev("t3", "trend_spotted", trend="pineapple pizza debate"))["verdict"], "pass")


class Integrations(unittest.TestCase):
    def test_chain_stall_and_complete(self):
        evs = [ev("r1", "trend_spotted", dept="research"),
               ev("p1", "product_created", dept="design", parent="r1"),
               ev("l1", "listing_live", dept="sales", parent="p1")]
        st = agent.chain_state(evs)["r1"]
        self.assertEqual(st["next"], "order_placed")
        evs += [ev("o1", "order_placed", parent="l1"), ev("m1", "margin_update", dept="finance", parent="o1")]
        self.assertIsNone(agent.chain_state(evs)["r1"]["next"])

    def test_connection_map(self):
        m = agent.connection_map([ev("x", "dept_online", dept="finance")])
        self.assertTrue(m["finance"]["connected"])
        self.assertFalse(m["legal"]["connected"])
        self.assertEqual(len(m), 13)


class Time(unittest.TestCase):
    def test_hub_millis_timestamp(self):
        self.assertAlmostEqual(agent.parse_ts("2026-10-20T00:17:12.738Z") - agent.parse_ts("2026-10-20T00:17:12Z"), 0.738, 3)


class Loop(unittest.TestCase):
    def test_step_emits_once_and_ignores_own_events(self):
        out = []
        a = agent.Agent(emit=lambda *x, **k: out.append((x, k)))
        a.qa = lambda *x, **k: None
        a.seen = set()
        evs = [ev("o9", "order_placed", price=30, pod_cost=12),
               ev("t9", "trend_spotted", dept="research", trend="Pokemon fan art"),
               ev("fin-o9", "order_placed", dept="finance", price=1, pod_cost=1) | {"actor": "dev3-finance"}]
        a.step(evs, t=0)
        a.step(evs, t=0)
        depts = [x[0][0] for x in out if x[0][4].get("kind") != "chain_watch"]
        self.assertEqual(depts, ["finance", "legal"])
        self.assertEqual(out[1][0][2], "needs_approval")


class GrokWiring(unittest.TestCase):
    def _agent(self):
        out = []
        a = agent.Agent(emit=lambda *x, **k: out.append((x, k)))
        a.seen = set(); a.qa = lambda *x, **k: out.append((("QA",) + x, k))
        return a, out

    def test_no_key_marks_finance_and_legal_mock(self):
        a, out = self._agent()
        a.step([ev("o1", "order_placed", price=30, pod_cost=12), ev("t1", "trend_spotted", dept="research", trend="Tiny hat frogs")], t=0)
        modes = {x[0][0]: x[1].get("mode") for x in out if x[0][4].get("kind") != "chain_watch"}
        self.assertEqual(modes, {"finance": "mock", "legal": "mock"})
        self.assertEqual(out[0][0][4]["grok"]["mode"], "mock")

    def test_live_grok_sets_live_and_can_escalate_a_pass(self):
        a, out = self._agent()
        live_op = {"mode": "live", "verdict": "flag", "opinion": "FLAG looks like a real band logo", "engine": "xai"}
        live_sum = {"mode": "live", "summary": "Healthy margin.", "engine": "xai"}
        with mock.patch.object(agent.grok, "legal_opinion", return_value=live_op), \
             mock.patch.object(agent.grok, "margin_summary", return_value=live_sum):
            a.step([ev("t2", "trend_spotted", dept="research", trend="Tiny hat frogs"),
                    ev("o2", "order_placed", price=30, pod_cost=12)], t=0)
        legal = [x for x in out if x[0][0] == "legal"][0]
        self.assertEqual((legal[0][2], legal[1]["mode"], legal[0][4]["verdict"]), ("needs_approval", "live", "flag"))
        self.assertTrue(any(i.startswith("grok:") for i in legal[0][4]["issues"]))
        self.assertTrue(any(x[0][0] == "QA" for x in out))
        fin = [x for x in out if x[0][0] == "finance"][0]
        self.assertEqual((fin[1]["mode"], fin[0][4]["grok"]["summary"]), ("live", "Healthy margin."))

    def test_under_floor_routes_pricing_through_qa_bridge(self):
        a, out = self._agent()
        with mock.patch.object(agent.qa_bridge, "margin_check") as mc:
            a.step([ev("o3", "order_placed", price=12, pod_cost=10)], t=0)
        mc.assert_called_once()
        self.assertEqual(mc.call_args[0][0], "fin-o3")

    def test_order_hop_uses_buyer_window_not_bot_window(self):
        a, out = self._agent()
        evs = [ev("t4", "trend_spotted", dept="research", trend="Tiny hat frogs", ts="2026-10-20T00:00:00Z"),
               ev("p4", "product_created", dept="design", parent="t4", ts="2026-10-20T00:00:01Z"),
               ev("l4", "listing_live", dept="design", parent="p4", ts="2026-10-20T00:00:02Z")]
        t0 = agent.parse_ts("2026-10-20T00:00:02Z")
        a.step(evs, t=t0 + agent.STALL_SEC + 5)
        self.assertFalse([x for x in out if x[0][4].get("kind") == "chain_stalled"])
        a.step(evs, t=t0 + agent.STALL_ORDER_SEC + 5)
        st = [x for x in out if x[0][4].get("kind") == "chain_stalled"]
        self.assertEqual(st[0][0][4]["missing"], "order_placed")


def task(tid, dept, title, text="", parent="req-1"):
    return {"task_id": tid, "dept": dept, "status": "queued", "summary": f"Task: {title}", "ts": "2026-10-20T00:00:00Z",
            "actor": "auto", "mode": "live", "parent_id": parent,
            "output": {"kind": "task", "title": title, "detail": {"text": text, "source": "dev1-orchestrator", "kind": "routed_task"}}}


class TaskPickup(unittest.TestCase):
    def _run(self, evs):
        out = []
        a = agent.Agent(emit=lambda *x, **k: out.append((x, k)))
        a.seen = set(); a.qa = lambda *x, **k: out.append((("QA",) + x, k))
        a.step(evs, t=agent.parse_ts("2026-10-20T00:00:05Z"))
        return a, out

    def test_finance_task_claims_then_reports_margin(self):
        lst = ev("p1", "listing_live", dept="design", product={"price_usd": 6.0, "cost_usd": 1.6})
        order = ev("o1", "order_placed", dept="ops", parent="p1", qty=2, revenue_usd=12.0, cost_usd=3.2)
        prod = ev("p1", "product_created", dept="design", status="running")   # hub: same task_id, no price at top level
        a, out = self._run([prod, lst, order, task("finance-1", "finance", "Margin report for Pulse Studio")])
        mine = [x for x in out if x[0][1] == "finance-1"]
        self.assertEqual([x[0][2] for x in mine], ["running", "done"])
        self.assertTrue(all(x[1]["parent_id"] == "req-1" for x in mine))
        r = [x for x in out if x[0][1] == "fin-finance-1"]
        self.assertEqual(r[0][1]["parent_id"], "finance-1")   # reply is its own task, linked to the incoming task
        rep = r[0][0][4]
        self.assertEqual((rep["kind"], rep["orders_priced"], rep["revenue"], rep["margin"]), ("finance_report", 1, 12.0, 8.15))

    def test_legal_task_flag_goes_to_founder_and_qa(self):
        a, out = self._run([task("legal-1", "legal", "Review launch copy", "New Nike x Pulse tee drop")])
        mine = [x for x in out if x[0][1] == "legal-1" and x[0][0] == "legal"]
        self.assertEqual([x[0][2] for x in mine], ["running", "needs_approval"])
        self.assertEqual([x for x in out if x[0][1] == "legal-legal-1"][0][0][4]["verdict"], "flag")
        self.assertTrue(any(x[0][0] == "QA" for x in out))

    def test_task_addressed_by_for_dept(self):
        t = task("legal-9", "legal", "Contract terms", "ships in 5 days"); t["dept"] = "orchestrator"; t["output"]["for_dept"] = "legal"
        a, out = self._run([t])
        mine = [x for x in out if x[0][1] == "legal-9"]
        self.assertEqual([(x[0][0], x[0][2], x[1]["parent_id"]) for x in mine], [("legal", "running", "req-1"), ("legal", "done", "req-1")])
        r = [x for x in out if x[0][1] == "legal-legal-9"]
        self.assertEqual((r[0][0][2], r[0][1]["parent_id"], r[0][0][4]["kind"]), ("done", "legal-9", "legal_precheck"))
        self.assertEqual(r[0][1]["mode"], "mock")   # no real Grok call -> mock

    def test_legal_task_pass_is_done(self):
        a, out = self._run([task("legal-2", "legal", "Check terms of sale", "Printed on demand, ships in 5 days")])
        self.assertEqual([x[0][2] for x in out if x[0][1] == "legal-2"], ["running", "done"])

    def test_integrations_task_returns_status(self):
        a, out = self._run([ev("t1", "trend_spotted", dept="research", trend="Tiny hat frogs"),
                            task("integrations-1", "integrations", "Webhook connector status")])
        mine = [x for x in out if x[0][1] == "integrations-1"]
        self.assertEqual([x[0][2] for x in mine], ["running", "done"])
        r = [x for x in out if x[0][1] == "int-integrations-1"]
        self.assertEqual((r[0][0][2], r[0][1]["parent_id"], r[0][0][4]["kind"]), ("done", "integrations-1", "integration_status"))

    def test_claimed_or_other_dept_tasks_are_skipped_and_once_only(self):
        t = task("finance-2", "finance", "Revenue")
        moved = dict(t, status="running", actor="someone")
        other = task("sales-1", "sales", "Not ours")
        a, out = self._run([t, moved, other])
        self.assertFalse([x for x in out if x[0][1] in ("finance-2", "sales-1")])
        a2, out2 = self._run([task("finance-3", "finance", "Revenue")])
        a2.step([task("finance-3", "finance", "Revenue")], t=0)
        self.assertEqual(len([x for x in out2 if x[0][1] == "finance-3"]), 2)

    def test_task_work_error_posts_failed(self):
        with mock.patch.object(agent, "finance_report", side_effect=RuntimeError("boom")):
            a, out = self._run([task("finance-4", "finance", "Revenue")])
        self.assertEqual([x[0][2] for x in out if x[0][1] == "finance-4"], ["running", "failed"])


if __name__ == "__main__":
    unittest.main()
