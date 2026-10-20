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
        result = spot(settings=settings, force=True)
        listed = EventsClient(settings).get_events(task_id=result["task_id"], dept="research", limit=20)
    except Exception as exc:
        print(f"FAIL smoke: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    events = listed.get("events") or []
    match = [ev for ev in events if ev.get("task_id") == result["task_id"]]
    spotted = next((ev for ev in match if (ev.get("output") or {}).get("kind") == "trend_spotted"), None)
    accepted = next((ev for ev in match if (ev.get("output") or {}).get("kind") == "trend_accepted"), None)
    output = (spotted.get("output") if spotted else {}) or {}
    acc = (accepted.get("output") if accepted else {}) or {}
    ok = (
        spotted is not None
        and accepted is not None
        and spotted.get("dept") == "research"
        and spotted.get("status") == "done"
        and spotted.get("mode") in ("live", "mock")
        and output.get("kind") == "trend_spotted"
        and output.get("source") == "x"
        and output.get("trend")
        and output.get("why")
        and (spotted.get("mode") == "live" or output.get("fallback") == "backup_fixture")
        and accepted.get("actor") == "dev1-trend"
        and accepted.get("mode") == spotted.get("mode")
        and acc.get("kind") == "trend_accepted"
        and acc.get("trend") == output.get("trend")
        and acc.get("source") == "x"
        and "STAND-IN" not in (accepted.get("summary") or "")
        and "standin" not in acc
    )
    print(json.dumps({"ok": ok, "mode": result["mode"], "spotted": spotted, "accepted": accepted}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
