"""UserUsage persists per-(user, day) counts."""

import datetime as dt

from sqlalchemy import select

from app.models.usage import UserUsage


async def test_user_usage_insert_and_read(db_session, test_user):
    today = dt.date(2026, 5, 28)
    db_session.add(UserUsage(user_id=test_user["id"], day=today, count=3))
    await db_session.commit()

    result = await db_session.execute(
        select(UserUsage).where(UserUsage.user_id == test_user["id"])
    )
    row = result.scalars().first()
    assert row.count == 3
    assert row.day == today
