"""India clock helpers.

Every timestamp is stored in UTC and rendered in Asia/Kolkata, so the clock on the
dashboard and the "today" grouping always agree with the operator's day.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """Normalize a stored timestamp.

    SQLite drops the offset on write, so values come back naive even though they were
    written as UTC. Assuming UTC for naive values keeps ordering and day grouping right.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_ist(value: datetime | None) -> datetime | None:
    normalized = as_utc(value)
    return normalized.astimezone(IST) if normalized else None


def fmt_ist(value: datetime | None, pattern: str = "%d-%m-%Y %H:%M") -> str:
    local = to_ist(value)
    return local.strftime(pattern) if local else "—"


def ist_today() -> date:
    return datetime.now(IST).date()


def ist_day_bounds_utc(day: date | None = None) -> tuple[datetime, datetime]:
    target = day or ist_today()
    start_local = datetime.combine(target, time.min, tzinfo=IST)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def ist_clock_now() -> dict[str, str]:
    """Values for the server-rendered clock; the browser keeps it ticking."""
    now = datetime.now(IST)
    return {
        "date": now.strftime("%d-%m-%Y"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
    }
