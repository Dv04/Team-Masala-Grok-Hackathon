#!/usr/bin/env python3
"""Smoke against a running departments service (./start.sh, port 8810).

Posts a Pulse kickoff and checks that an orchestrator event landed and that
exactly one research task was created for that request. Does not require a key.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import orchestrator as orch

BASE = os.environ.get("DEPT_SERVICE_URL", "http://127.0.0.1:8810").rstrip("/")


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=10) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    checks = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))
        print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""))

    try:
        health = get("/health")
        check("GET /health", health.get("ok") is True, json.dumps(health)[:180])
    except Exception as e:
        print(f"FAIL dept service not reachable at {BASE}: {e}")
        print("Start it with: cd departments && ./start.sh")
        return 2

    os.environ.pop("XAI_API_KEY", None)
    try:
        result = orch.Orchestrator(client=orch.DeptClient(BASE), max_tasks=4).pulse(
            "Launch something on what's trending today"
        )
    except Exception as e:
        print(f"FAIL pulse raised: {e}")
        return 1

    check("pulse intent", result.get("intent") == "pulse", result.get("intent", ""))
    check("mode mock without key", result.get("mode") == "mock", result.get("mode", ""))
    routed = result.get("tasks") or []
    check("only research routed", [t.get("dept") for t in routed] == ["research"],
          ",".join(t.get("dept", "") for t in routed))
    req = result["request_id"]
    try:
        ev = get(f"/api/events?dept=orchestrator&limit=50")
        mine = [e for e in ev.get("events", []) if e.get("task_id") == req]
        check("orchestrator events posted", len(mine) >= 1, f"{len(mine)} for {req}")
        check("event mode honest", all(e.get("mode") == "mock" for e in mine), "")
    except Exception as e:
        check("orchestrator events posted", False, str(e))
    try:
        tasks = get("/api/tasks?dept=research")
        mine_tasks = [t for t in tasks.get("tasks", []) if t.get("parent_id") == req]
        check("research task created", len(mine_tasks) == 1, f"{len(mine_tasks)}")
        chain = [t for t in tasks.get("tasks", []) if t.get("parent_id") == req and t.get("dept") != "research"]
        # tasks endpoint is filtered by dept=research, so re-read unfiltered via events
    except Exception as e:
        check("research task created", False, str(e))
    try:
        all_ev = get("/api/events?limit=400")
        extra = [e for e in all_ev.get("events", [])
                 if e.get("parent_id") == req and e.get("dept") in orch.PULSE_CHAIN_DEPTS
                 and (e.get("output") or {}).get("kind") == "task"
                 and (e.get("actor") in (orch.ACTOR, "auto"))]
        # Tasks the orchestrator created would be kind=task on that dept with this parent.
        # A stand-in chain may also emit events; only fail if WE created those tasks.
        created = [e for e in extra if (e.get("output") or {}).get("kind") == "task"]
        check("no chain steps routed by orchestrator", len(created) == 0, f"{len(created)} extra task events")
    except Exception as e:
        check("no chain steps routed by orchestrator", False, str(e))

    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\n{passed}/{len(checks)} passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.URLError as e:
        print(f"FAIL {e}")
        raise SystemExit(2)
