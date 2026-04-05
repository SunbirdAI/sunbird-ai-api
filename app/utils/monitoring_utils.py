import re
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.monitoring import (
    get_logs_by_username_since,
    get_recent_logs_by_username,
    get_usage_stats_by_username,
)
from app.schemas.monitoring import EndpointLog

VALID_TIME_RANGES = {
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "2h": timedelta(hours=2),
    "6h": timedelta(hours=6),
    "12h": timedelta(hours=12),
    "24h": timedelta(hours=24),
    "1d": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "60d": timedelta(days=60),
    "90d": timedelta(days=90),
}


def parse_time_range(time_range: str) -> timedelta:
    """Parse a time range string and return a timedelta.

    Accepts keys from VALID_TIME_RANGES (e.g. '5m', '1h', '7d').
    Falls back to parsing '<int>d' for backward compatibility.
    Raises ValueError for unrecognised formats.
    """
    if time_range in VALID_TIME_RANGES:
        return VALID_TIME_RANGES[time_range]

    # Backward compat: bare integer-days like "14d"
    match = re.fullmatch(r"(\d+)d", time_range)
    if match:
        return timedelta(days=int(match.group(1)))

    raise ValueError(f"Invalid time_range: {time_range}")


def _bucket_format(td: timedelta) -> str:
    """Return a strftime format appropriate for the given duration."""
    total_seconds = td.total_seconds()
    if total_seconds <= 3600:  # <= 1 hour: bucket by minute
        return "%H:%M"
    elif total_seconds <= 86400:  # <= 24 hours: bucket by hour
        return "%b %d %H:00"
    else:  # > 24 hours: bucket by day
        return "%Y-%m-%d"


def _generate_labels(start: datetime, td: timedelta) -> list[str]:
    """Generate ordered time-bucket labels covering the range [start, now]."""
    fmt = _bucket_format(td)
    total_seconds = td.total_seconds()
    labels = []
    now = datetime.now()

    if total_seconds <= 3600:
        # Step by 1 minute
        steps = int(total_seconds / 60)
        for i in range(steps + 1):
            t = start + timedelta(minutes=i)
            if t > now:
                break
            labels.append(t.strftime(fmt))
    elif total_seconds <= 86400:
        # Step by 1 hour
        steps = int(total_seconds / 3600)
        for i in range(steps + 1):
            t = start + timedelta(hours=i)
            if t > now:
                break
            labels.append(t.strftime(fmt))
    else:
        # Step by 1 day
        days = int(total_seconds / 86400)
        for i in range(days):
            t = start + timedelta(days=i)
            if t > now:
                break
            labels.append(t.strftime(fmt))
        # Always include today
        today_label = now.strftime(fmt)
        if not labels or labels[-1] != today_label:
            labels.append(today_label)

    return labels


async def aggregate_usage_for_user(db: AsyncSession, username: str):
    rows = await get_usage_stats_by_username(db, username)
    aggregates = defaultdict(int)
    for endpoint, count in rows:
        aggregates[endpoint] = count
    return aggregates


async def get_dashboard_stats(db: AsyncSession, username: str, time_range: str = "7d"):
    td = parse_time_range(time_range)
    fmt = _bucket_format(td)

    # 1. Total usage counts (all time)
    aggregates = await aggregate_usage_for_user(db, username)

    # 2. Recent activity
    recent_logs_db = await get_recent_logs_by_username(db, username, limit=50)
    recent_activity = [EndpointLog.model_validate(log) for log in recent_logs_db]

    # 3. Time-range data
    start_date = datetime.now() - td
    recent_period_logs = await get_logs_by_username_since(db, username, start_date)

    # Bucket logs using the same format as labels
    daily_volume = defaultdict(int)
    daily_latency_sum = defaultdict(float)
    daily_latency_count = defaultdict(int)
    endpoint_daily_volumes = defaultdict(lambda: defaultdict(int))

    for log in recent_period_logs:
        if log.date:
            bucket = log.date.strftime(fmt)
            daily_volume[bucket] += 1
            daily_latency_sum[bucket] += log.time_taken
            daily_latency_count[bucket] += 1
            endpoint_daily_volumes[log.endpoint][bucket] += 1

    # Generate labels
    day_labels = _generate_labels(start_date, td)

    volume_counts = [daily_volume.get(label, 0) for label in day_labels]
    latency_data = []
    for label in day_labels:
        count = daily_latency_count.get(label, 0)
        if count > 0:
            latency_data.append(daily_latency_sum[label] / count)
        else:
            latency_data.append(0)

    # Per-endpoint time series
    endpoint_chart_data = {}
    for endpoint in aggregates.keys():
        endpoint_chart_data[endpoint] = [
            endpoint_daily_volumes[endpoint].get(label, 0) for label in day_labels
        ]

    # 4. Latency Distribution (Histogram buckets)
    latency_buckets = {
        "<100ms": 0,
        "100-500ms": 0,
        "500ms-1s": 0,
        "1s-2s": 0,
        ">2s": 0,
    }
    for log in recent_period_logs:
        ms = log.time_taken * 1000
        if ms < 100:
            latency_buckets["<100ms"] += 1
        elif ms < 500:
            latency_buckets["100-500ms"] += 1
        elif ms < 1000:
            latency_buckets["500ms-1s"] += 1
        elif ms < 2000:
            latency_buckets["1s-2s"] += 1
        else:
            latency_buckets[">2s"] += 1

    return {
        "usage_counts": aggregates,
        "recent_activity": recent_activity,
        "chart_data": {"labels": day_labels, "data": volume_counts},
        "endpoint_chart_data": {"labels": day_labels, "datasets": endpoint_chart_data},
        "latency_chart": {"labels": day_labels, "data": latency_data},
        "distribution_chart": {
            "labels": list(aggregates.keys()),
            "data": list(aggregates.values()),
        },
        "latency_distribution": {
            "labels": list(latency_buckets.keys()),
            "data": list(latency_buckets.values()),
        },
    }
