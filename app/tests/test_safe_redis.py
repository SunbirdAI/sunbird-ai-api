"""SafeRedis swallows connection errors and exposes a usable async API."""

import fakeredis.aioredis
import pytest
import redis.exceptions

from app.services.redis_client import SafeRedis


@pytest.fixture
def healthy_safe_redis():
    backend = fakeredis.aioredis.FakeRedis(decode_responses=True)
    return SafeRedis(backend)


async def test_set_and_get_roundtrip(healthy_safe_redis):
    await healthy_safe_redis.set("foo", "bar", ex=30)
    assert await healthy_safe_redis.get("foo") == "bar"


async def test_incr_returns_count(healthy_safe_redis):
    assert await healthy_safe_redis.incr("counter") == 1
    assert await healthy_safe_redis.incr("counter") == 2


async def test_ping_healthy(healthy_safe_redis):
    assert await healthy_safe_redis.is_healthy() is True


async def test_get_swallows_connection_error(monkeypatch):
    class BrokenBackend:
        async def get(self, key):
            raise redis.exceptions.ConnectionError("upstream down")

    safe = SafeRedis(BrokenBackend())
    assert await safe.get("foo") is None


async def test_set_swallows_timeout(monkeypatch):
    class SlowBackend:
        async def set(self, *args, **kwargs):
            raise redis.exceptions.TimeoutError("read timeout")

    safe = SafeRedis(SlowBackend())
    # Should not raise.
    assert await safe.set("foo", "bar", ex=10) is None


async def test_incr_returns_none_on_error():
    class BrokenBackend:
        async def incr(self, key, amount=1):
            raise redis.exceptions.RedisError("EVICTED")

    safe = SafeRedis(BrokenBackend())
    assert await safe.incr("counter") is None


async def test_is_healthy_false_on_failure():
    class BrokenBackend:
        async def ping(self):
            raise redis.exceptions.ConnectionError("nope")

    safe = SafeRedis(BrokenBackend())
    assert await safe.is_healthy() is False
