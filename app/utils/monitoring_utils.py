from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.monitoring import (
    get_logs_by_username,
    get_recent_logs_by_username,
    get_logs_by_username_since,
    get_usage_stats_by_username,
)
from app.schemas.monitoring import EndpointLog


async def aggregate_usage_for_user(db: AsyncSession, username: str):
    # Use SQL aggregation for performance
    rows = await get_usage_stats_by_username(db, username)
    aggregates = defaultdict(int)
    for endpoint, count in rows:
        aggregates[endpoint] = count
    return aggregates


async def get_dashboard_stats(db: AsyncSession, username: str, time_range: str = "7d"):
    # 1. Total usage counts
    aggregates = await aggregate_usage_for_user(db, username)

    # 2. Recent activity
    recent_logs_db = await get_recent_logs_by_username(db, username, limit=50)
    recent_activity = [EndpointLog.model_validate(log) for log in recent_logs_db]

    # 3. Daily request volume & Latency (dynamic time range)
    # Parse time_range: "7d", "30d", "90d"
    days = int(time_range.rstrip('d')) if time_range.endswith('d') else 7
    start_date = datetime.now() - timedelta(days=days)
    recent_period_logs = await get_logs_by_username_since(db, username, start_date)

    daily_volume = defaultdict(int)
    daily_latency_sum = defaultdict(float)
    daily_latency_count = defaultdict(int)
    # Track per-endpoint daily volumes
    endpoint_daily_volumes = defaultdict(lambda: defaultdict(int))
    
    for log in recent_period_logs:
        if log.date:
            day = log.date.strftime("%a")  # Mon, Tue, etc.
            daily_volume[day] += 1
            daily_latency_sum[day] += log.time_taken
            daily_latency_count[day] += 1
            # Track per endpoint
            endpoint_daily_volumes[log.endpoint][day] += 1

    # Generate labels for the time range
    day_labels = []
    volume_counts = []
    latency_data = []
    
    for i in range(days):
        date = datetime.now() - timedelta(days=days - 1 - i)
        day_name = date.strftime("%b %d") if days > 7 else date.strftime("%a")
        day_labels.append(day_name)
        volume_counts.append(daily_volume.get(day_name, 0))
        
        # Calculate average latency for the day
        count = daily_latency_count.get(day_name, 0)
        if count > 0:
            avg_latency = daily_latency_sum.get(day_name, 0) / count
        else:
            avg_latency = 0
        latency_data.append(avg_latency)
    
    # Generate per-endpoint time series data
    endpoint_chart_data = {}
    for endpoint in aggregates.keys():
        endpoint_data = []
        for i in range(days):
            date = datetime.now() - timedelta(days=days - 1 - i)
            day_name = date.strftime("%b %d") if days > 7 else date.strftime("%a")
            endpoint_data.append(endpoint_daily_volumes[endpoint].get(day_name, 0))
        endpoint_chart_data[endpoint] = endpoint_data

    # 4. Latency Distribution (Histogram buckets)
    # Buckets: <100ms, 100-500ms, 500ms-1s, 1s-2s, >2s
    latency_buckets = {
        "<100ms": 0,
        "100-500ms": 0,
        "500ms-1s": 0,
        "1s-2s": 0,
        ">2s": 0
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
            "data": list(aggregates.values())
        },
        "latency_distribution": {
            "labels": list(latency_buckets.keys()),
            "data": list(latency_buckets.values())
        }
    }
