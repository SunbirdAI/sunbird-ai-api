from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError
from app.deps import get_current_user, get_db
from app.schemas.users import User
from app.utils.monitoring_utils import get_dashboard_stats, parse_time_range

router = APIRouter()


@router.get("/usage")
async def get_usage_stats(
    time_range: str = "7d",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get usage statistics for the current user"""
    try:
        parse_time_range(time_range)
    except ValueError:
        raise BadRequestError(
            f"Invalid time_range '{time_range}'. "
            "Use values like 5m, 15m, 30m, 1h, 2h, 6h, 12h, 24h, 7d, 30d, 60d, 90d."
        )

    username = current_user.username
    stats = await get_dashboard_stats(db, username, time_range=time_range)

    usage_data = []
    for endpoint, count in stats["usage_counts"].items():
        usage_data.append(
            {
                "endpoint": endpoint,
                "used": count,
            }
        )

    return {
        "usage": usage_data,
        "recent_activity": stats["recent_activity"],
        "chart_data": stats["chart_data"],
        "endpoint_chart_data": stats["endpoint_chart_data"],
        "latency_chart": stats["latency_chart"],
        "distribution_chart": stats["distribution_chart"],
        "latency_distribution": stats["latency_distribution"],
        "account_type": current_user.account_type.value,
        "organization": current_user.organization,
    }
