#!/usr/bin/env python3
"""Smoke against a locally running departments service (departments/start.sh, port 8810).

Posts one listing_live event and waits until marketing has emitted running, then a
sandbox draft (done or needs_approval) with needs_qa true. Prints the events it saw.
"""
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

DEPT = os.environ.get("DEPARTMENTS_URL", "http://127.0.0.1:8810").rstrip("/")
WEBHOOK = os.environ.get("MARKETING_WEBHOOK_URL", "http://127.0.0.1:8899/pulse")


def get(path):
    with urllib.request.urlopen(DEPT + path, timeout=5) as res:
        return json.loads(res.read().decode())


def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(DEPT + path, data=data, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as res:
        return json.loads(res.read().decode())


def main():
    try:
        health = get("/health")
    except Exception as e:
        print(f"FAIL departments service not reachable at {DEPT}/health ({e})")
        print("Start it with: departments/start.sh")
        return 1
    print("departments", json.dumps(health))
    try:
        with urllib.request.urlopen(WEBHOOK.replace("/pulse", "/health"), timeout=3) as res:
            print("marketing", res.read().decode())
    except Exception as e:
        print(f"FAIL marketing bot not reachable at {WEBHOOK} ({e})")
        print("Start it with: dev1/marketing_bot/run.sh")
        return 1

    task = f"smoke-listing-{int(time.time())}"
    ev = {
        "dept": "sales",
        "task_id": task,
        "actor": "dev1-marketing-smoke",
        "status": "done",
        "summary": "smoke listing_live",
        "mode": "mock",
        "output": {
            "kind": "listing_live",
            "product": {
                "type": "tee",
                "title": "Smoke Test Tee",
                "tagline": "A shirt from the timeline",
                "price": 24,
                "cost": 8,
                "trend": "smoke trend",
            },
            "url": "https://example.com/smoke-tee",
            "action": {"type": "listing_published"},
        },
    }
    posted = post("/api/events", ev)
    print("posted listing_live", posted.get("ok"), task)
    deadline = time.time() + 20
    seen = []
    while time.time() < deadline:
        data = get(f"/api/events?task_id=mkt-{task}&limit=20")
        seen = data.get("events") or []
        statuses = [e.get("status") for e in seen]
        final = [e for e in seen if (e.get("output") or {}).get("drafts")]
        if "running" in statuses and final:
            break
        time.sleep(0.5)
    else:
        print("FAIL timed out waiting for marketing drafts")
        print(json.dumps(seen, indent=2)[:2000])
        return 1
    running = [e for e in seen if e["status"] == "running"]
    final = [e for e in seen if (e.get("output") or {}).get("drafts")][-1]
    ok_running = bool(running)
    ok_qa = final["output"].get("needs_qa") is True and final["output"].get("posted") is False
    ok_status = final["status"] in ("done", "needs_approval", "failed")
    ok_dept = final["dept"] == "marketing"
    print("running_events", len(running), "final_status", final["status"], "mode", final["mode"])
    print("summary", final["summary"])
    drafts = final["output"]["drafts"]
    print("x_post", drafts.get("x_post"))
    print("engine", drafts.get("engine"))
    if not (ok_running and ok_qa and ok_status and ok_dept):
        print("FAIL", {"running": ok_running, "needs_qa": ok_qa, "status": ok_status, "dept": ok_dept})
        return 1
    print("PASS marketing smoke")
    return 0


if __name__ == "__main__":
    sys.exit(main())
