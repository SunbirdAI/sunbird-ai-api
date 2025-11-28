from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.deps import get_db, get_current_user
from app.utils.monitoring_utils import aggregate_usage_for_user, get_dashboard_stats
from app.schemas.users import User

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/usage")
async def get_usage_stats(
    time_range: str = "7d",  # 7d, 30d, 90d
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get usage statistics for the current user"""
    username = current_user.username
    stats = await get_dashboard_stats(db, username, time_range=time_range)
    
    # Format the response
    usage_data = []
    for endpoint, count in stats["usage_counts"].items():
        usage_data.append({
            "endpoint": endpoint,
            "used": count,
        })
    
    return {
        "usage": usage_data,
        "recent_activity": stats["recent_activity"],
        "chart_data": stats["chart_data"],
        "endpoint_chart_data": stats["endpoint_chart_data"],
        "latency_chart": stats["latency_chart"],
        "distribution_chart": stats["distribution_chart"],
        "account_type": current_user.account_type.value,
        "organization": current_user.organization
    }
