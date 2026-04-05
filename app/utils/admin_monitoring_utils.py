from collections import defaultdict
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.admin_monitoring import (
    get_all_logs_since,
    get_logs_by_organization,
    get_logs_by_organization_type,
    get_logs_by_sector,
    get_recent_logs_all,
    get_usage_stats_all,
)
from app.schemas.monitoring import EndpointLog
from app.utils.monitoring_utils import (
    _bucket_format,
    _generate_labels,
    parse_time_range,
)


async def get_admin_overview_stats(db: AsyncSession, time_range: str = "7d"):
    """Aggregate stats across all users for admin overview."""
    td = parse_time_range(time_range)
    fmt = _bucket_format(td)

    # All-time usage counts
    rows = await get_usage_stats_all(db)
    aggregates = defaultdict(int)
    for endpoint, count in rows:
        aggregates[endpoint] = count

    # Recent activity
    recent_logs_db = await get_recent_logs_all(db, limit=200)
    recent_activity = [EndpointLog.model_validate(log) for log in recent_logs_db]

    # Time-range data
    start_date = datetime.now() - td
    period_logs = await get_all_logs_since(db, start_date)

    chart_data = _build_chart_data(period_logs, fmt, start_date, td)

    return {
        "usage_counts": dict(aggregates),
        "recent_activity": recent_activity,
        **chart_data,
    }


async def get_admin_org_stats(
    db: AsyncSession, organization: str, time_range: str = "7d"
):
    """Aggregate stats filtered by organization, with per-user breakdown."""
    td = parse_time_range(time_range)
    fmt = _bucket_format(td)

    start_date = datetime.now() - td
    period_logs = await get_logs_by_organization(db, organization, start_date)

    # All-time counts for this org (re-use period logs for simplicity; could query separately)
    aggregates = defaultdict(int)
    for log in period_logs:
        aggregates[log.endpoint] += 1

    recent_activity = [
        EndpointLog.model_validate(log)
        for log in sorted(
            period_logs,
            key=lambda log_entry: log_entry.date or datetime.min,
            reverse=True,
        )[:200]
    ]

    chart_data = _build_chart_data(period_logs, fmt, start_date, td)

    # Per-user breakdown
    user_breakdown = defaultdict(lambda: defaultdict(int))
    user_total = defaultdict(int)
    for log in period_logs:
        user_breakdown[log.username][log.endpoint] += 1
        user_total[log.username] += 1

    per_user = []
    for username in sorted(user_total, key=user_total.get, reverse=True):
        per_user.append(
            {
                "username": username,
                "total_requests": user_total[username],
                "endpoints": dict(user_breakdown[username]),
            }
        )

    return {
        "organization": organization,
        "usage_counts": dict(aggregates),
        "recent_activity": recent_activity,
        "per_user_breakdown": per_user,
        **chart_data,
    }


async def get_admin_org_type_stats(
    db: AsyncSession, org_type: str, time_range: str = "7d"
):
    """Aggregate stats filtered by organization type."""
    td = parse_time_range(time_range)
    fmt = _bucket_format(td)

    start_date = datetime.now() - td
    period_logs = await get_logs_by_organization_type(db, org_type, start_date)

    aggregates = defaultdict(int)
    for log in period_logs:
        aggregates[log.endpoint] += 1

    recent_activity = [
        EndpointLog.model_validate(log)
        for log in sorted(
            period_logs,
            key=lambda log_entry: log_entry.date or datetime.min,
            reverse=True,
        )[:200]
    ]

    chart_data = _build_chart_data(period_logs, fmt, start_date, td)

    return {
        "organization_type": org_type,
        "usage_counts": dict(aggregates),
        "recent_activity": recent_activity,
        **chart_data,
    }


async def get_admin_sector_stats(db: AsyncSession, sector: str, time_range: str = "7d"):
    """Aggregate stats filtered by sector."""
    td = parse_time_range(time_range)
    fmt = _bucket_format(td)

    start_date = datetime.now() - td
    period_logs = await get_logs_by_sector(db, sector, start_date)

    aggregates = defaultdict(int)
    for log in period_logs:
        aggregates[log.endpoint] += 1

    recent_activity = [
        EndpointLog.model_validate(log)
        for log in sorted(
            period_logs,
            key=lambda log_entry: log_entry.date or datetime.min,
            reverse=True,
        )[:200]
    ]

    chart_data = _build_chart_data(period_logs, fmt, start_date, td)

    return {
        "sector": sector,
        "usage_counts": dict(aggregates),
        "recent_activity": recent_activity,
        **chart_data,
    }


def _build_chart_data(logs, fmt: str, start_date, td):
    """Build volume, latency, endpoint, and distribution chart data from logs."""
    daily_volume = defaultdict(int)
    daily_latency_sum = defaultdict(float)
    daily_latency_count = defaultdict(int)
    endpoint_daily_volumes = defaultdict(lambda: defaultdict(int))
    endpoint_totals = defaultdict(int)

    for log in logs:
        if log.date:
            bucket = log.date.strftime(fmt)
            daily_volume[bucket] += 1
            daily_latency_sum[bucket] += log.time_taken
            daily_latency_count[bucket] += 1
            endpoint_daily_volumes[log.endpoint][bucket] += 1
            endpoint_totals[log.endpoint] += 1

    day_labels = _generate_labels(start_date, td)

    volume_counts = [daily_volume.get(label, 0) for label in day_labels]

    latency_data = []
    for label in day_labels:
        count = daily_latency_count.get(label, 0)
        if count > 0:
            latency_data.append(daily_latency_sum[label] / count)
        else:
            latency_data.append(0)

    endpoint_chart_data = {}
    for endpoint in endpoint_totals:
        endpoint_chart_data[endpoint] = [
            endpoint_daily_volumes[endpoint].get(label, 0) for label in day_labels
        ]

    # Latency distribution buckets
    latency_buckets = {
        "<100ms": 0,
        "100-500ms": 0,
        "500ms-1s": 0,
        "1s-2s": 0,
        ">2s": 0,
    }
    for log in logs:
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
        "chart_data": {"labels": day_labels, "data": volume_counts},
        "endpoint_chart_data": {"labels": day_labels, "datasets": endpoint_chart_data},
        "latency_chart": {"labels": day_labels, "data": latency_data},
        "distribution_chart": {
            "labels": list(endpoint_totals.keys()),
            "data": list(endpoint_totals.values()),
        },
        "latency_distribution": {
            "labels": list(latency_buckets.keys()),
            "data": list(latency_buckets.values()),
        },
    }
