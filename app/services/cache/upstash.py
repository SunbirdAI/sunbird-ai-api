"""Upstash/Redis-backed ``CacheBackend`` implementation.

Values must be JSON-serialisable — passing a non-serialisable value to
``set`` raises ``TypeError`` from ``json.dumps`` (caller-side bug, not a
transport failure).

Transport failures from ``SafeRedis`` (Redis unreachable, timeout) surface
as ``None`` on read and silent no-ops on write; callers treat ``None`` as
a cache miss in the usual read-through pattern. Corrupt JSON in storage
also surfaces as a miss (``get`` returns ``None``).
"""

from __future__ import annotations

import json
from typing import Any, Optional

from app.services.cache import CacheBackend
from app.services.redis_client import SafeRedis


class UpstashCache(CacheBackend):
    def __init__(self, client: SafeRedis) -> None:
        self._client = client

    async def get(self, key: str) -> Optional[Any]:
        raw = await self._client.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        await self._client.set(key, json.dumps(value), ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)
