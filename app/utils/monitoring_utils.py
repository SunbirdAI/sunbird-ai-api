from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.monitoring import get_logs_by_username
from app.schemas.monitoring import EndpointLog


async def aggregate_usage_for_user(db: AsyncSession, username: str):
    # TODO: Make this load only data for the current month.
    logs = await get_logs_by_username(db, username)
    logs = [EndpointLog.model_validate(endpoint_log) for endpoint_log in logs]
    aggregates = defaultdict(int)
    for endpoint_log in logs:
        aggregates[endpoint_log.endpoint] += 1

    return aggregates
