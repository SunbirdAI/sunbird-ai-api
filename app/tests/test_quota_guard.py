"""``check_quota`` raises RateLimitError when the daily cap is exceeded."""

import datetime as dt
from types import SimpleNamespace

import fakeredis.aioredis
import pytest

from app.core.exceptions import RateLimitError
from app.services.quota_service import QuotaService
from app.services.redis_client import SafeRedis
from app.utils.quota_guard import check_quota

pytestmark = pytest.mark.real_quota


async def test_check_quota_passes_under_cap(db_session, test_user):
    user = SimpleNamespace(id=test_user["id"], account_type="free")
    svc = QuotaService(
        redis=SafeRedis(fakeredis.aioredis.FakeRedis(decode_responses=True)),
        today=lambda: dt.date(2026, 5, 28),
    )
    await check_quota(svc, db_session, user)  # does not raise


async def test_check_quota_raises_at_cap(db_session, test_user):
    user = SimpleNamespace(id=test_user["id"], account_type="free")
    svc = QuotaService(
        redis=SafeRedis(fakeredis.aioredis.FakeRedis(decode_responses=True)),
        today=lambda: dt.date(2026, 5, 28),
    )
    for _ in range(500):
        await check_quota(svc, db_session, user)
    with pytest.raises(RateLimitError) as exc_info:
        await check_quota(svc, db_session, user)
    assert exc_info.value.retry_after is not None
    assert exc_info.value.retry_after > 0
