"""Spot one X trend and POST trend_spotted for dept research.

Live: Grok Responses API with x_search and web_search.
No key, or an unusable reply: fixtures/backup_trend.json and mode=mock.
source stays "x" either way so dev4's Pulse chain starts. mode is the honesty bit.
"""
import json
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

_DEV1 = Path(__file__).resolve().parents[1]
if str(_DEV1) not in sys.path:
    sys.path.insert(0, str(_DEV1))

from common.config import Settings, load_settings
from common.events import EventError, EventsClient, redact
from common.grok import GrokClient, GrokError

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "backup_trend.json"
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)
RECENT_WINDOW = timedelta(minutes=30)


def norm_trend(value) -> str:
    return str(value or "").strip().casefold()


def _parse_ts(value):
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def find_recent_trend(events, trend: str, *, now=None, window: timedelta = RECENT_WINDOW):
    """Return a prior trend_spotted for this trend, or None.

    A hit is the same trend (trimmed, case-insensitive) with kind trend_spotted,
    timestamped inside `window` or sitting in the returned page with no timestamp.
    Older than `window` does not count.
    """
    want = norm_trend(trend)
    if not want:
        return None
    now = now or datetime.now(timezone.utc)
    found = None
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        out = ev.get("output") or {}
        if out.get("kind") != "trend_spotted":
            continue
        if norm_trend(out.get("trend")) != want:
            continue
        ts = _parse_ts(ev.get("ts"))
        if ts is not None and now - ts > window:
            continue
        found = ev
    return found


def _recent_research(events: EventsClient):
    listed = events.get_events(dept="research", limit=200)
    if not isinstance(listed, dict):
        return []
    rows = listed.get("events") or []
    return rows if isinstance(rows, list) else []


def load_backup() -> tuple[str, str]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    trend = str(data.get("trend") or "").strip()
    why = str(data.get("why") or "").strip()
    if not trend or not why:
        raise ValueError(f"backup fixture {FIXTURE} needs trend and why")
    return trend, why


def parse_trend(text: str) -> tuple[str, str] | None:
    if not text:
        return None
    cleaned = _FENCE.sub("", text.strip())
    match = re.search(r"\{.*\}", cleaned, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    trend = str(data.get("trend") or "").strip()
    why = str(data.get("why") or "").strip()
    if not trend or not why:
        return None
    return trend[:180], why[:500]


def _prompt(query: str) -> str:
    return (
        "You are Pulse Studio research. Use x_search to find one thing trending on X "
        "that can become a sticker, a tee, or a poster.\n"
        'Return ONLY JSON: {"trend": "short name", "why": "one sentence"}.\n'
        "No prices, no discounts, no email addresses, no phone numbers, no guarantees.\n"
        f"Hint: {query}"
    )


def spot(
    query: str = "what people on X want as a sticker, tee, or poster right now",
    *,
    settings: Settings | None = None,
    grok: GrokClient | None = None,
    events: EventsClient | None = None,
    force: bool = False,
) -> dict:
    settings = settings or load_settings()
    grok = grok or GrokClient(settings)
    events = events or EventsClient(settings)
    trend = why = None
    mode = "mock"
    fallback = True
    if grok.mode == "live":
        try:
            result = grok.respond(
                _prompt(query),
                tools=[{"type": "x_search"}, {"type": "web_search"}],
            )
            parsed = parse_trend(result.text) if result.mode == "live" else None
            if parsed:
                trend, why = redact(parsed[0]), redact(parsed[1])
                if trend and why and "[redacted]" not in trend:
                    mode = "live"
                    fallback = False
                else:
                    trend = why = None
        except (GrokError, OSError, ValueError):
            trend = why = None
    if trend is None:
        trend, why = load_backup()
        trend, why = redact(trend), redact(why)
        mode = "mock"
        fallback = True
    output = {"kind": "trend_spotted", "trend": trend, "why": why, "source": "x"}
    if fallback:
        output["fallback"] = "backup_fixture"
    if not force:
        try:
            prior = find_recent_trend(_recent_research(events), trend)
        except (EventError, OSError):
            prior = None
        if prior:
            message = (
                f"skip: trend {trend!r} was already posted as trend_spotted "
                f"(task {prior.get('task_id')}). Nothing posted."
            )
            return {
                "skipped": True,
                "task_id": prior.get("task_id"),
                "mode": mode,
                "fallback": fallback,
                "output": output,
                "message": message,
            }
    task_id = "trend-" + uuid.uuid4().hex[:8]
    posted = events.post_event(
        dept="research",
        task_id=task_id,
        status="done",
        summary=f"Trend spotted: {trend}",
        mode=mode,
        actor="dev1-trend",
        output=output,
    )
    # Same shape as departments/lib/standins.py research stand-in, without the
    # [STAND-IN] label or standin flags. Same task_id so the stand-in sees a real
    # research event and stays quiet. mode matches this run, not a fake live.
    accepted = events.post_event(
        dept="research",
        task_id=task_id,
        status="done",
        summary=f"Research: trend accepted '{trend}'"[:200],
        mode=mode,
        actor="dev1-trend",
        output={"kind": "trend_accepted", "trend": trend, "source": output["source"]},
        parent_id=task_id,
    )
    return {
        "task_id": task_id,
        "mode": mode,
        "fallback": fallback,
        "output": output,
        "posted": posted,
        "accepted": accepted,
        "skipped": False,
    }


def _force_from(args: list[str]) -> bool:
    return os.environ.get("TREND_FORCE", "") == "1" or "--force" in args


def main(argv: list[str] | None = None) -> int:
    args = [a for a in (sys.argv[1:] if argv is None else argv) if a != "--force"]
    force = _force_from(list(sys.argv[1:] if argv is None else argv))
    try:
        result = spot(" ".join(args), force=force) if args else spot(force=force)
    except Exception as exc:
        print(f"trend bot failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("Is the departments service up? DEPARTMENTS_BASE_URL defaults to http://127.0.0.1:8810", file=sys.stderr)
        return 1
    if result.get("skipped"):
        print(result["message"])
        return 0
    print(json.dumps(result, indent=2, default=str))
    event = (result.get("posted") or {}).get("event") or {}
    print(
        f"posted research {result['task_id']} mode={result['mode']} "
        f"fallback={result['fallback']} server_status={event.get('status', 'n/a')}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
