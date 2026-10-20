"""Unit tests for dev3 depts (no hub needed): python -m unittest dev3/test_agent.py"""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["DEV3_SEEN"] = os.path.join(tempfile.mkdtemp(), "seen.json")
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
        self.assertEqual(round(o["margin_pct"], 2), 0.68)
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
        a.qa = lambda *x: None
        a.seen = set()
        evs = [ev("o9", "order_placed", price=30, pod_cost=12),
               ev("t9", "trend_spotted", dept="research", trend="Pokemon fan art"),
               ev("fin-o9", "order_placed", dept="finance", price=1, pod_cost=1) | {"actor": "dev3-finance"}]
        a.step(evs, t=0)
        a.step(evs, t=0)
        depts = [x[0][0] for x in out]
        self.assertEqual(depts, ["finance", "legal"])
        self.assertEqual(out[1][0][2], "needs_approval")


if __name__ == "__main__":
    unittest.main()
