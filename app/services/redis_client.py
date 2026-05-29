"""Async Redis client wrapper that fails open on connection errors.

`SafeRedis` is the only Redis surface the rest of the app should call. Every
method swallows ``redis.exceptions.RedisError`` and returns ``None`` (reads) or
``None`` / no-op (writes). Callers treat ``None`` as "Redis unavailable, fall
back to the durable source" without scattering try/except blocks.

The wrapped client is created once at startup via ``get_redis_client()`` and
re-used for the process lifetime. Connection settings target Upstash (TLS,
small pool, fail-fast timeouts).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import redis.asyncio as aioredis
import redis.exceptions

from app.core.config import settings

# NOTE: do NOT rename either import. Specifically, `import redis.asyncio as
# redis` followed by `import redis.exceptions` silently rebinds the local
# name `redis` to the top-level (synchronous) redis package, so
# `redis.from_url(...)` returns a sync client. The sync client's `.ping()`
# returns a bool, and `await True` raises "object bool can't be used in
# 'await' expression". Using a distinct `aioredis` alias avoids this trap.

logger = logging.getLogger(__name__)


class SafeRedis:
    """Thin wrapper around ``redis.asyncio.Redis`` that fails open."""

    def __init__(self, backend: Any) -> None:
        self._backend = backend

    @property
    def backend(self) -> Any:
        """Expose the underlying client for callers that need pipelines etc.

        Callers using ``backend`` directly accept that errors are NOT swallowed.
        """
        return self._backend

    async def is_healthy(self) -> bool:
        try:
            await self._backend.ping()
            return True
        except redis.exceptions.RedisError as exc:
            logger.debug("Redis ping failed: %s", exc)
            return False
        except Exception as exc:  # noqa: BLE001 — fakeredis raises generic Exception in some paths
            logger.debug("Redis ping failed (non-RedisError): %s", exc)
            return False

    async def get(self, key: str) -> Optional[str]:
        try:
            return await self._backend.get(key)
        except redis.exceptions.RedisError as exc:
            logger.warning("Redis GET %s failed: %s", key, exc)
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ex: Optional[int] = None,
    ) -> None:
        try:
            await self._backend.set(key, value, ex=ex)
        except redis.exceptions.RedisError as exc:
            logger.warning("Redis SET %s failed: %s", key, exc)

    async def incr(self, key: str, amount: int = 1) -> Optional[int]:
        try:
            return await self._backend.incr(key, amount)
        except redis.exceptions.RedisError as exc:
            logger.warning("Redis INCR %s failed: %s", key, exc)
            return None

    async def expire(self, key: str, seconds: int) -> None:
        try:
            await self._backend.expire(key, seconds)
        except redis.exceptions.RedisError as exc:
            logger.warning("Redis EXPIRE %s failed: %s", key, exc)

    async def delete(self, key: str) -> None:
        try:
            await self._backend.delete(key)
        except redis.exceptions.RedisError as exc:
            logger.warning("Redis DELETE %s failed: %s", key, exc)


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_safe_redis: Optional[SafeRedis] = None


async def init_redis_client() -> Optional[SafeRedis]:
    """Build and validate the process-wide ``SafeRedis``.

    Returns ``None`` when ``settings.redis_url`` is unset or when the initial
    ping fails. Callers must tolerate ``None`` and use durable storage instead.
    """
    global _safe_redis

    if not settings.redis_url:
        logger.info("REDIS_URL not configured; Redis features disabled")
        _safe_redis = None
        return None

    try:
        backend = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=settings.redis_socket_timeout,
            socket_connect_timeout=settings.redis_socket_connect_timeout,
            health_check_interval=settings.redis_health_check_interval,
            retry_on_timeout=True,
            max_connections=settings.redis_max_connections,
        )
        await backend.ping()
        logger.info("Redis connection established")
        _safe_redis = SafeRedis(backend)
        return _safe_redis
    except Exception as exc:  # noqa: BLE001 — startup must not crash
        logger.warning("Redis init failed (%s); continuing without Redis", exc)
        _safe_redis = None
        return None


def get_redis_client() -> Optional[SafeRedis]:
    """Return the cached ``SafeRedis`` singleton or ``None`` if uninitialised."""
    return _safe_redis
