import asyncio

from app.services.cache.in_memory import InMemoryTTLCache


async def test_set_then_get_returns_value():
    cache = InMemoryTTLCache()
    await cache.set("k1", {"a": 1}, ttl_seconds=60)
    assert await cache.get("k1") == {"a": 1}


async def test_get_missing_key_returns_none():
    cache = InMemoryTTLCache()
    assert await cache.get("missing") is None


async def test_get_expired_key_returns_none(monkeypatch):
    cache = InMemoryTTLCache()
    now = {"t": 1000.0}
    monkeypatch.setattr("app.services.cache.in_memory.time.monotonic", lambda: now["t"])
    await cache.set("k1", "v", ttl_seconds=10)
    now["t"] = 1005.0
    assert await cache.get("k1") == "v"
    now["t"] = 1011.0
    assert await cache.get("k1") is None


async def test_delete_removes_key():
    cache = InMemoryTTLCache()
    await cache.set("k1", "v", ttl_seconds=60)
    await cache.delete("k1")
    assert await cache.get("k1") is None


async def test_delete_missing_key_is_noop():
    cache = InMemoryTTLCache()
    await cache.delete("never-set")  # should not raise


async def test_concurrent_sets_are_safe():
    cache = InMemoryTTLCache()

    async def setter(i: int):
        await cache.set(f"k{i}", i, ttl_seconds=60)

    await asyncio.gather(*(setter(i) for i in range(50)))
    for i in range(50):
        assert await cache.get(f"k{i}") == i
