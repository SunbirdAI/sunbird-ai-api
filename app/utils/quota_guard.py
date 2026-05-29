"""Thin helper used inside router handlers to enforce day/month quotas.

Sits next to the existing SlowAPI per-minute decorator: SlowAPI handles
``per_minute``, this raises on ``per_day`` and ``per_month``. Routers call it
explicitly so we don't depend on framework-level magic.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RateLimitError
from app.services.quota_service import QuotaService


async def check_quota(
    quota: QuotaService,
    db: AsyncSession,
    user,
) -> None:
    result = await quota.check_and_consume(db, user)
    if result.allowed:
        return
    scope_msg = {
        "day": "Daily quota exceeded",
        "month": "Monthly quota exceeded",
    }.get(result.scope or "", "Quota exceeded")
    raise RateLimitError(
        message=scope_msg,
        retry_after=result.retry_after_seconds,
    )
