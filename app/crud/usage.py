"""CRUD operations for ``UserUsage`` rows.

Callers own the transaction (no commit here), per project convention.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage import UserUsage


async def increment_daily(
    db: AsyncSession,
    user_id: int,
    day: dt.date,
    units: int = 1,
) -> None:
    """Upsert: add ``units`` to the (user_id, day) row, creating it if absent.

    SQLite (tests) uses ``INSERT OR IGNORE`` + ``UPDATE`` since it lacks the
    PostgreSQL ``ON CONFLICT DO UPDATE`` syntax we'd otherwise use.
    """
    dialect = db.bind.dialect.name if db.bind else ""

    if dialect == "postgresql":
        stmt = (
            pg_insert(UserUsage)
            .values(user_id=user_id, day=day, count=units)
            .on_conflict_do_update(
                index_elements=["user_id", "day"],
                set_={"count": UserUsage.count + units},
            )
        )
        await db.execute(stmt)
        return

    # SQLite fallback: SELECT, then INSERT or UPDATE.
    # NOT atomic under concurrent writers — acceptable here because the only
    # SQLite consumer is the in-memory test DB (single process, single writer).
    # Production runs PostgreSQL and uses the ON CONFLICT branch above.
    existing = await db.execute(
        select(UserUsage).where(
            UserUsage.user_id == user_id,
            UserUsage.day == day,
        )
    )
    row = existing.scalars().first()
    if row is None:
        db.add(UserUsage(user_id=user_id, day=day, count=units))
    else:
        row.count = row.count + units


async def get_day_count(db: AsyncSession, user_id: int, day: dt.date) -> int:
    result = await db.execute(
        select(UserUsage.count).where(
            UserUsage.user_id == user_id,
            UserUsage.day == day,
        )
    )
    val = result.scalars().first()
    return int(val) if val is not None else 0


async def get_month_total(db: AsyncSession, user_id: int, year: int, month: int) -> int:
    start = dt.date(year, month, 1)
    end = dt.date(year + (month // 12), (month % 12) + 1, 1)
    result = await db.execute(
        select(func.coalesce(func.sum(UserUsage.count), 0)).where(
            UserUsage.user_id == user_id,
            UserUsage.day >= start,
            UserUsage.day < end,
        )
    )
    return int(result.scalar_one() or 0)
