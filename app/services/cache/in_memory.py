"""In-memory TTL cache, scoped to a single process/Cloud Run instance."""

import asyncio
import time
from typing import Any


class InMemoryTTLCache:
    """Simple per-process TTL cache using a dict and monotonic time.

    Per-Cloud Run instance: each replica keeps its own cache. Acceptable
    for admin-only endpoints where GA data lags several hours regardless.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        async with self._lock:
            self._store[key] = (value, time.monotonic() + ttl_seconds)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)
