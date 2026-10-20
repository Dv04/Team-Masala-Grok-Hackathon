"""Post one trend_spotted and read it back from the departments service.

Usage (from dev1/): python3 trend_bot/smoke.py
Requires DEPARTMENTS_BASE_URL (default http://127.0.0.1:8810) already running.
Does not bind port 8899 (reserved for the marketing bot).
"""
import json
import sys
from pathlib import Path

_DEV1 = Path(__file__).resolve().parents[1]
if str(_DEV1) not in sys.path:
    sys.path.insert(0, str(_DEV1))

from common.config import load_settings
from common.events import EventsClient
from trend_bot.bot import spot


def main() -> int:
    settings = load_settings()
    try:
        result = spot(settings=settings)
        listed = EventsClient(settings).get_events(task_id=result["task_id"], dept="research", limit=20)
    except Exception as exc:
        print(f"FAIL smoke: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    events = listed.get("events") or []
    match = [ev for ev in events if ev.get("task_id") == result["task_id"]]
    output = (match[-1].get("output") if match else {}) or {}
    ok = (
        bool(match)
        and match[-1].get("dept") == "research"
        and match[-1].get("status") == "done"
        and match[-1].get("mode") in ("live", "mock")
        and output.get("kind") == "trend_spotted"
        and output.get("source") == "x"
        and output.get("trend")
        and output.get("why")
        and (match[-1].get("mode") == "live" or output.get("fallback") == "backup_fixture")
    )
    print(json.dumps({"ok": ok, "mode": result["mode"], "event": match[-1] if match else None}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
