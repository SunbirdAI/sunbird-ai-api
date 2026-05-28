"""Upstash CacheBackend honours TTL and tolerates Redis failures."""

import fakeredis.aioredis

from app.services.cache.upstash import UpstashCache
from app.services.redis_client import SafeRedis


async def test_set_get_delete_roundtrip():
    backend = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache = UpstashCache(SafeRedis(backend))

    await cache.set("k", {"v": 1}, ttl_seconds=60)
    assert await cache.get("k") == {"v": 1}
    await cache.delete("k")
    assert await cache.get("k") is None


async def test_get_returns_none_on_redis_failure():
    class Broken:
        async def get(self, key):
            from redis.exceptions import ConnectionError as RCE
            raise RCE("down")

    cache = UpstashCache(SafeRedis(Broken()))
    assert await cache.get("k") is None
