from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.monitoring import (
    get_logs_by_username,
    get_recent_logs_by_username,
    get_logs_by_username_since,
)
from app.schemas.monitoring import EndpointLog


async def aggregate_usage_for_user(db: AsyncSession, username: str):
    # TODO: Make this load only data for the current month.
    logs = await get_logs_by_username(db, username)
    logs = [EndpointLog.model_validate(endpoint_log) for endpoint_log in logs]
    aggregates = defaultdict(int)
    for endpoint_log in logs:
        aggregates[endpoint_log.endpoint] += 1

    return aggregates


async def get_dashboard_stats(db: AsyncSession, username: str):
    # 1. Total usage counts
    aggregates = await aggregate_usage_for_user(db, username)

    # 2. Recent activity
    recent_logs_db = await get_recent_logs_by_username(db, username, limit=5)
    recent_activity = [EndpointLog.model_validate(log) for log in recent_logs_db]

    # 3. Daily request volume & Latency (last 7 days)
    seven_days_ago = datetime.now() - timedelta(days=7)
    recent_period_logs = await get_logs_by_username_since(db, username, seven_days_ago)

    daily_volume = defaultdict(int)
    daily_latency_sum = defaultdict(float)
    daily_latency_count = defaultdict(int)
    
    for log in recent_period_logs:
        if log.date:
            day = log.date.strftime("%a")  # Mon, Tue, etc.
            daily_volume[day] += 1
            daily_latency_sum[day] += log.time_taken
            daily_latency_count[day] += 1

    # Generate labels for the last 7 days
    days = []
    volume_counts = []
    latency_data = []
    
    for i in range(7):
        date = datetime.now() - timedelta(days=6 - i)
        day_name = date.strftime("%a")
        days.append(day_name)
        volume_counts.append(daily_volume.get(day_name, 0))
        
        # Calculate average latency for the day
        count = daily_latency_count.get(day_name, 0)
        if count > 0:
            avg_latency = daily_latency_sum.get(day_name, 0) / count
        else:
            avg_latency = 0
        latency_data.append(avg_latency)

    return {
        "usage_counts": aggregates,
        "recent_activity": recent_activity,
        "chart_data": {"labels": days, "data": volume_counts},
        "latency_chart": {"labels": days, "data": latency_data},
        "distribution_chart": {
            "labels": list(aggregates.keys()),
            "data": list(aggregates.values())
        }
    }
