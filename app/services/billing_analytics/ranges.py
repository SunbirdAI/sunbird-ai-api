"""Resolve named or explicit date ranges into concrete UTC datetimes."""

from __future__ import annotations

from datetime import datetime, timedelta


def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 string, tolerating a trailing 'Z', returning naive UTC."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def floor_to_quantum(dt: datetime, quantum_seconds: int) -> datetime:
    """Floor ``dt`` to the nearest lower multiple of ``quantum_seconds`` within its day.

    Stabilizes "now" so repeated and concurrent identical billing requests resolve to
    the same range (and therefore the same cache key) within the quantum window —
    giving consistent results instead of a freshly-fluctuating live fetch per call.
    """
    q = max(quantum_seconds, 1)
    seconds = dt.hour * 3600 + dt.minute * 60 + dt.second
    floored = (seconds // q) * q
    return dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
        seconds=floored
    )


def resolve_range(
    range_name: str | None,
    start: str | None,
    end: str | None,
    now: datetime,
) -> tuple[datetime, datetime]:
    """Return (start, end) UTC datetimes for a named or custom range.

    Named ranges: today, yesterday, last_7_days, last_30_days, last_90_days,
    this_month, last_month. 'custom' (or any explicit start/end) requires both
    `start` and `end`. Raises ValueError on invalid input.
    """
    if range_name == "custom" and not (start and end):
        raise ValueError("custom range requires both 'start' and 'end'")
    if range_name in (None, "", "custom") and (start or end):
        if not (start and end):
            raise ValueError("custom range requires both 'start' and 'end'")
        return _parse_iso(start), _parse_iso(end)

    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    mapping = {
        "today": (today, now),
        "yesterday": (today - timedelta(days=1), today),
        "last_7_days": (now - timedelta(days=7), now),
        "last_30_days": (now - timedelta(days=30), now),
        "last_90_days": (now - timedelta(days=90), now),
        "this_month": (today.replace(day=1), now),
    }
    if range_name == "last_month":
        first_this = today.replace(day=1)
        last_month_end = first_this
        last_month_start = (first_this - timedelta(days=1)).replace(day=1)
        return last_month_start, last_month_end
    if range_name in mapping:
        return mapping[range_name]
    # Default when nothing supplied.
    if range_name in (None, "", "custom"):
        return now - timedelta(days=30), now
    raise ValueError(f"Unknown range '{range_name}'")
