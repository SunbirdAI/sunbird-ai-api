"""Per-day, per-user usage counters used to enforce daily/monthly quotas.

One row per (user_id, day). Monthly totals are computed by summing rows
where ``day`` falls within a given YYYY-MM. Redis is a hot cache in front of
this table; this is the durable source of truth.

``user_id`` is intentionally a plain ``Integer`` rather than a foreign key
to ``users.id``: QuotaService only writes ``current_user.id`` from the
authenticated request, so referential integrity is enforced at the
application boundary. Keeping the column FK-free also avoids forcing
SQLite test fixtures to enable foreign-key enforcement.
"""

import datetime as dt

from sqlalchemy import Column, Date, Integer, PrimaryKeyConstraint
from sqlalchemy.sql import expression

from app.database.db import Base


class UserUsage(Base):
    __tablename__ = "user_usage"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "day", name="pk_user_usage"),
    )

    user_id = Column(Integer, nullable=False, index=True)
    day = Column(Date, nullable=False, index=True, default=dt.date.today)
    count = Column(Integer, nullable=False, server_default=expression.literal(0))
