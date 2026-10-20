"""Spot one X trend and POST trend_spotted for dept research.

Live: Grok Responses API with x_search and web_search.
No key, or an unusable reply: fixtures/backup_trend.json and mode=mock.
source stays "x" either way so dev4's Pulse chain starts. mode is the honesty bit.
"""
import json
import re
import sys
import uuid
from pathlib import Path

_DEV1 = Path(__file__).resolve().parents[1]
if str(_DEV1) not in sys.path:
    sys.path.insert(0, str(_DEV1))

from common.config import Settings, load_settings
from common.events import EventsClient, redact
from common.grok import GrokClient, GrokError

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "backup_trend.json"
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)


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
    return {
        "task_id": task_id,
        "mode": mode,
        "fallback": fallback,
        "output": output,
        "posted": posted,
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        result = spot(" ".join(args)) if args else spot()
    except Exception as exc:
        print(f"trend bot failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("Is the departments service up? DEPARTMENTS_BASE_URL defaults to http://127.0.0.1:8810", file=sys.stderr)
        return 1
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
