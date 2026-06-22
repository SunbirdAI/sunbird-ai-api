from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import distinct, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.monitoring import EndpointLog


async def get_all_logs_since(db: AsyncSession, since: datetime) -> List[EndpointLog]:
    result = await db.execute(select(EndpointLog).filter(EndpointLog.date >= since))
    return result.scalars().all()


async def get_recent_logs_all(db: AsyncSession, limit: int = 200) -> List[EndpointLog]:
    result = await db.execute(
        select(EndpointLog).order_by(EndpointLog.date.desc()).limit(limit)
    )
    return result.scalars().all()


async def get_logs_by_organization(
    db: AsyncSession, organization: str, since: datetime
) -> List[EndpointLog]:
    result = await db.execute(
        select(EndpointLog)
        .filter(EndpointLog.organization == organization)
        .filter(EndpointLog.date >= since)
    )
    return result.scalars().all()


async def get_logs_by_organization_type(
    db: AsyncSession, org_type: str, since: datetime
) -> List[EndpointLog]:
    result = await db.execute(
        select(EndpointLog)
        .filter(EndpointLog.organization_type == org_type)
        .filter(EndpointLog.date >= since)
    )
    return result.scalars().all()


async def get_logs_by_sector(
    db: AsyncSession, sector: str, since: datetime
) -> List[EndpointLog]:
    """Filter logs where the JSON sector column contains the given sector value.

    sector is stored as a JSON list (e.g. ["Health", "Education"]).
    SQLite (tests) uses json_each; PostgreSQL uses the @> containment operator.
    We fall back to loading all rows and filtering in Python so that both
    backends are supported without dialect-specific SQL.
    """
    result = await db.execute(select(EndpointLog).filter(EndpointLog.date >= since))
    all_logs = result.scalars().all()
    return [
        log
        for log in all_logs
        if log.sector and sector in (log.sector if isinstance(log.sector, list) else [])
    ]


async def get_usage_stats_all(
    db: AsyncSession,
) -> List[Tuple[str, int]]:
    result = await db.execute(
        select(EndpointLog.endpoint, func.count(EndpointLog.id)).group_by(
            EndpointLog.endpoint
        )
    )
    return result.all()


async def get_unique_organizations(db: AsyncSession) -> List[str]:
    result = await db.execute(
        select(distinct(EndpointLog.organization)).filter(
            EndpointLog.organization.isnot(None)
        )
    )
    return [row[0] for row in result.all() if row[0]]


async def get_unique_organization_types(db: AsyncSession) -> List[str]:
    result = await db.execute(
        select(distinct(EndpointLog.organization_type)).filter(
            EndpointLog.organization_type.isnot(None)
        )
    )
    return [row[0] for row in result.all() if row[0]]


async def get_unique_sectors(db: AsyncSession) -> List[str]:
    """Return distinct sector values across all logs.

    Since sector is a JSON list column, we load all non-null values and
    flatten them in Python for cross-database compatibility.
    """
    result = await db.execute(
        select(EndpointLog.sector).filter(EndpointLog.sector.isnot(None))
    )
    sectors = set()
    for (sector_val,) in result.all():
        if isinstance(sector_val, list):
            sectors.update(sector_val)
    return sorted(sectors)


async def get_unique_users(
    db: AsyncSession, organization: Optional[str] = None
) -> List[str]:
    query = select(distinct(EndpointLog.username)).filter(
        EndpointLog.username.isnot(None)
    )
    if organization:
        query = query.filter(EndpointLog.organization == organization)
    result = await db.execute(query)
    return [row[0] for row in result.all() if row[0]]
