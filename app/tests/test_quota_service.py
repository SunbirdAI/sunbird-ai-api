"""QuotaService enforces day/month caps using Redis hot path + DB fallback."""

import datetime as dt
from types import SimpleNamespace

import fakeredis.aioredis
import pytest

from app.services.quota_service import QuotaService
from app.services.redis_client import SafeRedis

pytestmark = pytest.mark.real_quota


def _user(account_type: str = "free", user_id: int = 1):
    return SimpleNamespace(id=user_id, account_type=account_type)


@pytest.fixture
def safe_redis():
    return SafeRedis(fakeredis.aioredis.FakeRedis(decode_responses=True))


async def test_admin_is_unlimited(db_session, safe_redis):
    svc = QuotaService(redis=safe_redis, today=lambda: dt.date(2026, 5, 28))
    for _ in range(10):
        r = await svc.check_and_consume(db_session, _user("admin"))
        assert r.allowed


async def test_free_user_blocked_at_daily_cap(db_session, safe_redis):
    svc = QuotaService(redis=safe_redis, today=lambda: dt.date(2026, 5, 28))
    # 500/day for free. Consume 500 ⇒ allowed; 501st ⇒ denied.
    for i in range(500):
        r = await svc.check_and_consume(db_session, _user("free"))
        assert r.allowed, f"unexpected deny at iteration {i}"
    r = await svc.check_and_consume(db_session, _user("free"))
    assert not r.allowed
    assert r.scope == "day"
    assert r.retry_after_seconds > 0


async def test_redis_down_falls_back_to_db(db_session, safe_redis):
    # Force Redis to return None for INCR ⇒ service must read DB.
    class BrokenRedis(SafeRedis):
        async def incr(self, key, amount=1):
            return None

        async def get(self, key):
            return None

    svc = QuotaService(
        redis=BrokenRedis(safe_redis.backend),
        today=lambda: dt.date(2026, 5, 28),
    )
    r = await svc.check_and_consume(db_session, _user("free"))
    assert r.allowed  # 1st call passes via DB increment
