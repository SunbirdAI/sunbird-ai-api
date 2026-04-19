"""Pluggable cache backend for short-lived server-side caches.

The default `InMemoryTTLCache` is per-Cloud Run instance. See
`README.md` in this directory for migrating to a shared Upstash Redis
backend.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CacheBackend(Protocol):
    """Async cache interface. Values must be JSON-serialisable."""

    async def get(self, key: str) -> Any | None:
        ...

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        ...

    async def delete(self, key: str) -> None:
        ...


_instance: "CacheBackend | None" = None


def get_cache_backend() -> CacheBackend:
    """Return a process-wide cache backend singleton per current settings."""
    from app.core.config import settings

    global _instance
    if _instance is not None:
        return _instance

    if settings.cache_backend == "memory":
        from app.services.cache.in_memory import InMemoryTTLCache

        _instance = InMemoryTTLCache()
        return _instance

    raise ValueError(
        f"Unknown cache_backend '{settings.cache_backend}'. "
        "Supported: 'memory'. See app/services/cache/README.md."
    )
