"""Per-day / per-month quota enforcement with Redis hot path + DB durability.

Per-minute throttling stays inside SlowAPI. This service handles only the
longer windows.

Hot path:
    1. INCR ``quota:day:{user_id}:{YYYY-MM-DD}`` in Redis. If the new value
       is > daily cap, deny.
    2. INCR ``quota:month:{user_id}:{YYYY-MM}`` in Redis. If > monthly cap,
       deny. (Month counter is a cache; rebuilt from DB on miss.)
    3. Schedule a DB increment as a fire-and-forget task so the response
       isn't blocked on durable persistence.

Cold path (Redis returned None — likely down):
    1. Increment DB row synchronously.
    2. Read fresh day count + month total from DB.
    3. Compare to caps.

Admin tier short-circuits both paths.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.usage import get_day_count, get_month_total, increment_daily
from app.database.db import async_session_maker
from app.services.redis_client import SafeRedis, get_redis_client
from app.utils.rate_limit import TIER_QUOTAS

logger = logging.getLogger(__name__)

# Holds strong references to in-flight background DB persistence tasks so
# Python's GC doesn't drop them before they complete (asyncio.create_task
# only keeps a weak reference). See the Python asyncio docs:
# https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
_pending_persistence: set[asyncio.Task] = set()


@dataclass
class QuotaResult:
    allowed: bool
    scope: Optional[str] = None  # "day" | "month" | None
    remaining_day: Optional[int] = None
    remaining_month: Optional[int] = None
    retry_after_seconds: int = 0


def _seconds_until_end_of_day(now: dt.datetime) -> int:
    tomorrow = (now + dt.timedelta(days=1)).date()
    midnight = dt.datetime.combine(tomorrow, dt.time.min, tzinfo=now.tzinfo)
    return max(int((midnight - now).total_seconds()), 1)


def _seconds_until_end_of_month(now: dt.datetime) -> int:
    if now.month == 12:
        first_next = dt.datetime(now.year + 1, 1, 1, tzinfo=now.tzinfo)
    else:
        first_next = dt.datetime(now.year, now.month + 1, 1, tzinfo=now.tzinfo)
    return max(int((first_next - now).total_seconds()), 1)


class QuotaService:
    def __init__(
        self,
        redis: Optional[SafeRedis] = None,
        today: Callable[[], dt.date] = dt.date.today,
        now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
    ) -> None:
        self._redis = redis if redis is not None else get_redis_client()
        self._today = today
        self._now = now

    def _caps(self, account_type: str) -> tuple[Optional[int], Optional[int]]:
        tier = (account_type or "free").lower()
        if tier not in TIER_QUOTAS:
            tier = "free"
        q = TIER_QUOTAS[tier]
        return q["per_day"], q["per_month"]  # type: ignore[return-value]

    async def check_and_consume(
        self, db: AsyncSession, user
    ) -> QuotaResult:
        day_cap, month_cap = self._caps(getattr(user, "account_type", "free"))
        if day_cap is None and month_cap is None:
            return QuotaResult(allowed=True)

        today = self._today()
        ym = f"{today.year:04d}-{today.month:02d}"
        day_key = f"quota:day:{user.id}:{today.isoformat()}"
        month_key = f"quota:month:{user.id}:{ym}"

        # --- Hot path: Redis ---
        if self._redis is not None:
            day_count = await self._redis.incr(day_key)
            if day_count is not None:
                # First write of the day: set 26h TTL so eviction is bounded.
                if day_count == 1:
                    await self._redis.expire(day_key, 26 * 60 * 60)

                if day_cap is not None and day_count > day_cap:
                    return QuotaResult(
                        allowed=False,
                        scope="day",
                        remaining_day=0,
                        retry_after_seconds=_seconds_until_end_of_day(self._now()),
                    )

                month_count = await self._redis.incr(month_key)
                if month_count is not None and month_count == 1:
                    await self._redis.expire(month_key, 32 * 24 * 60 * 60)

                if (
                    month_cap is not None
                    and month_count is not None
                    and month_count > month_cap
                ):
                    return QuotaResult(
                        allowed=False,
                        scope="month",
                        remaining_month=0,
                        retry_after_seconds=_seconds_until_end_of_month(self._now()),
                    )

                # Async DB persistence so the response is not blocked.
                task = asyncio.create_task(
                    self._persist_daily(user.id, today, 1)
                )
                _pending_persistence.add(task)
                task.add_done_callback(_pending_persistence.discard)
                return QuotaResult(
                    allowed=True,
                    remaining_day=(
                        max(day_cap - day_count, 0) if day_cap is not None else None
                    ),
                    remaining_month=(
                        max(month_cap - (month_count or 0), 0)
                        if month_cap is not None
                        else None
                    ),
                )

        # --- Cold path: Redis down or returned None ---
        await increment_daily(db, user.id, today, 1)
        await db.commit()
        day_count_db = await get_day_count(db, user.id, today)
        month_total_db = await get_month_total(db, user.id, today.year, today.month)

        if day_cap is not None and day_count_db > day_cap:
            return QuotaResult(
                allowed=False,
                scope="day",
                remaining_day=0,
                retry_after_seconds=_seconds_until_end_of_day(self._now()),
            )
        if month_cap is not None and month_total_db > month_cap:
            return QuotaResult(
                allowed=False,
                scope="month",
                remaining_month=0,
                retry_after_seconds=_seconds_until_end_of_month(self._now()),
            )
        return QuotaResult(allowed=True)

    async def _persist_daily(self, user_id: int, day: dt.date, units: int) -> None:
        """Best-effort DB persistence in a background task. Never raises."""
        try:
            async with async_session_maker() as session:
                await increment_daily(session, user_id, day, units)
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Quota DB persistence failed (user=%s): %s", user_id, exc)


_quota_service: Optional[QuotaService] = None


def get_quota_service() -> QuotaService:
    global _quota_service
    if _quota_service is None:
        _quota_service = QuotaService()
    return _quota_service
