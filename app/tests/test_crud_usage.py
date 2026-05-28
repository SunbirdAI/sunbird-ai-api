"""CRUD helpers for daily increment and monthly aggregate."""

import datetime as dt

from app.crud.usage import (
    get_day_count,
    get_month_total,
    increment_daily,
)


async def test_increment_daily_creates_then_increments(db_session, test_user):
    day = dt.date(2026, 5, 28)
    await increment_daily(db_session, test_user["id"], day, 1)
    await db_session.commit()
    await increment_daily(db_session, test_user["id"], day, 4)
    await db_session.commit()

    assert await get_day_count(db_session, test_user["id"], day) == 5


async def test_get_month_total_sums_days(db_session, test_user):
    for d, n in [(1, 2), (5, 3), (28, 4)]:
        await increment_daily(
            db_session, test_user["id"], dt.date(2026, 5, d), n
        )
    await db_session.commit()
    total = await get_month_total(db_session, test_user["id"], 2026, 5)
    assert total == 9
