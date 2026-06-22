# Redis (Upstash) + Tiered Rate Limits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate Upstash Redis as the shared rate-limit backend with graceful fallback when Redis is unreachable, consolidate rate-limit wiring to a single Limiter, fix per-user key scoping, and add DB-backed per-day / per-month quotas per account tier.

**Architecture:** A thin `SafeRedis` wrapper swallows connection/timeout errors so callers never need try/except for transport failures. SlowAPI is configured with a Redis `storage_uri` and falls back to in-memory storage when Redis init fails at startup. Per-minute limits live entirely in Redis (cheap, ephemeral). Per-day uses Redis as a hot counter and a `UserUsage` DB table as the durable source of truth, so Upstash eviction can never under-count. Per-month is DB-primary with a Redis read-through cache. `FastAPILimiter` (initialised but never depended on) is removed.

**Tech Stack:** FastAPI, SlowAPI 0.1.9, redis-py 5.0.7 (async), Upstash Redis (TLS via `rediss://`), SQLAlchemy async + Alembic, fakeredis for tests.

---

## Required environment variables

| Variable | Required? | Example (local) | Example (Upstash) | Notes |
|---|---|---|---|---|
| `REDIS_URL` | Optional but recommended | `redis://localhost:6379/0` | `rediss://default:<PASSWORD>@<HOST>.upstash.io:6379` | TLS is negotiated automatically by the URI scheme (`rediss://`). Unset ⇒ app boots fine, rate limits use in-memory storage, daily/monthly quotas use DB only. |
| `REDIS_SOCKET_TIMEOUT` | Optional | (default `2.0`) | (default `2.0`) | Read timeout in seconds. Override if your Upstash region is far from Cloud Run. |
| `REDIS_SOCKET_CONNECT_TIMEOUT` | Optional | (default `2.0`) | (default `2.0`) | TCP connect timeout. |
| `REDIS_HEALTH_CHECK_INTERVAL` | Optional | (default `30`) | (default `30`) | Seconds between background pings (keeps idle connections alive). |
| `REDIS_MAX_CONNECTIONS` | Optional | (default `10`) | (default `10`) | Connection pool size per process. **Upstash free tier caps total concurrent connections at 100** — at 10 Cloud Run instances × 10 connections you're at the ceiling. Drop to 5 if you autoscale higher, or upgrade Upstash. |

**Upstash-specific note:** We use Upstash's TCP/TLS endpoint (the standard Redis protocol), not the HTTP REST endpoint. So `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` are **not** used by this app — leave them unset. The REST API is intended for edge runtimes (Cloudflare Workers, Vercel Edge) where TCP sockets aren't available; Cloud Run supports TCP natively.

---

## Phase 1 — Upstash client, graceful fallback, per-minute test

**Phase 1 exit criteria:**
- App boots whether Redis is reachable or not.
- SlowAPI counts requests against Upstash when configured; falls back to in-memory automatically when Redis is unreachable at startup, and per slowapi's `in_memory_fallback` when Redis errors mid-flight.
- All routers share a single `Limiter` instance keyed by `(account_type, user_or_ip)`, so free users get their own buckets.
- `FastAPILimiter` and its dead init are removed.
- A test verifies a Free-tier (and empty-`account_type` JWT) user gets a 429 on the 51st request inside a minute.

---

### Task 1: Add Redis settings to `Settings`

**Files:**
- Modify: `app/core/config.py` (after the `cache_backend` field around line 127)

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_redis_config.py`:

```python
"""Verify Redis-related settings are exposed via the Settings model."""

from app.core.config import Settings


def test_redis_settings_defaults(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    s = Settings(_env_file=None)
    assert s.redis_url is None
    assert s.redis_socket_timeout == 2.0
    assert s.redis_socket_connect_timeout == 2.0
    assert s.redis_health_check_interval == 30
    assert s.redis_max_connections == 10


def test_redis_url_read_from_env(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "rediss://default:abc@example.upstash.io:6379")
    s = Settings(_env_file=None)
    assert s.redis_url == "rediss://default:abc@example.upstash.io:6379"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest app/tests/test_redis_config.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'redis_url'` (or pydantic validation error).

- [ ] **Step 3: Add the fields to `Settings`**

In `app/core/config.py`, immediately after the `cache_backend` field (around line 130), add:

```python
    # Redis / Upstash Configuration
    redis_url: Optional[str] = Field(
        default=None,
        description=(
            "Redis connection URL. Use 'rediss://...' for Upstash (TLS). "
            "When unset, rate limiting falls back to in-memory storage."
        ),
    )
    redis_socket_timeout: float = Field(
        default=2.0,
        gt=0,
        description="redis-py socket read timeout in seconds (fail-fast for Upstash).",
    )
    redis_socket_connect_timeout: float = Field(
        default=2.0,
        gt=0,
        description="redis-py TCP connect timeout in seconds.",
    )
    redis_health_check_interval: int = Field(
        default=30,
        ge=0,
        description="redis-py background health-check interval in seconds.",
    )
    redis_max_connections: int = Field(
        default=10,
        ge=1,
        description="redis-py connection pool size (keep modest for Upstash quotas).",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest app/tests/test_redis_config.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Document the new env vars in `.env.example`**

Append the following block to `.env.example` (preserve existing content; add after the last related section):

```
# ---------------------------------------------------------------------------
# Redis / Upstash
# ---------------------------------------------------------------------------
# Use redis://... for a local Redis (no TLS) or rediss://... for Upstash (TLS).
# Leave unset to fall back to in-memory rate limiting + DB-only quotas.
# Example (local):   redis://localhost:6379/0
# Example (Upstash): rediss://default:<PASSWORD>@<HOST>.upstash.io:6379
REDIS_URL=

# Optional tuning (defaults are fine for most Upstash regions):
# REDIS_SOCKET_TIMEOUT=2.0
# REDIS_SOCKET_CONNECT_TIMEOUT=2.0
# REDIS_HEALTH_CHECK_INTERVAL=30
# REDIS_MAX_CONNECTIONS=10
```

- [ ] **Step 6: Commit**

```bash
git add app/core/config.py app/tests/test_redis_config.py .env.example
git commit -m "feat(config): add Redis/Upstash settings with sensible Upstash defaults"
```

---

### Task 2: Create `SafeRedis` wrapper

**Files:**
- Create: `app/services/redis_client.py`
- Test: `app/tests/test_safe_redis.py`

- [ ] **Step 1: Add fakeredis to dev requirements**

Append to `requirements-dev.txt`:

```
fakeredis==2.26.1
```

Run: `pip install -r requirements-dev.txt`

- [ ] **Step 2: Write the failing test**

Create `app/tests/test_safe_redis.py`:

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest app/tests/test_safe_redis.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.redis_client'`.

- [ ] **Step 4: Implement `SafeRedis`**

Create `app/services/redis_client.py`:

```python
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

import redis.asyncio as redis
import redis.exceptions

from app.core.config import settings

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
        backend = redis.from_url(
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest app/tests/test_safe_redis.py -v`
Expected: PASS (7 tests).

- [ ] **Step 6: Commit**

```bash
git add app/services/redis_client.py app/tests/test_safe_redis.py requirements-dev.txt
git commit -m "feat(redis): add SafeRedis wrapper with graceful failure semantics"
```

---

### Task 3: Implement Upstash cache backend

**Files:**
- Create: `app/services/cache/upstash.py`
- Modify: `app/services/cache/__init__.py`
- Test: `app/tests/test_cache_upstash.py`

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_cache_upstash.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest app/tests/test_cache_upstash.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `UpstashCache`**

Create `app/services/cache/upstash.py`:

```python
"""Upstash/Redis-backed ``CacheBackend`` implementation.

Values are JSON-serialised. Failures from ``SafeRedis`` surface as ``None``
on read and silent no-ops on write — the calling code is expected to treat
``None`` as a cache miss (typical read-through pattern).
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
```

- [ ] **Step 4: Wire the `upstash` branch in the factory**

Replace the body of `app/services/cache/__init__.py` (the `ValueError` block) so the previously declared `cache_backend = "upstash"` setting actually resolves:

```python
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

    if settings.cache_backend == "upstash":
        from app.services.cache.upstash import UpstashCache
        from app.services.redis_client import get_redis_client

        client = get_redis_client()
        if client is None:
            # Redis was unreachable at startup; fall back to in-memory so the
            # cache never raises. Logged at startup by init_redis_client.
            from app.services.cache.in_memory import InMemoryTTLCache

            _instance = InMemoryTTLCache()
            return _instance

        _instance = UpstashCache(client)
        return _instance

    raise ValueError(
        f"Unknown cache_backend '{settings.cache_backend}'. "
        "Supported: 'memory', 'upstash'."
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest app/tests/test_cache_upstash.py app/tests/test_cache_factory.py -v`
Expected: PASS (existing test_cache_factory.py keeps passing; new tests pass).

- [ ] **Step 6: Commit**

```bash
git add app/services/cache/upstash.py app/services/cache/__init__.py app/tests/test_cache_upstash.py
git commit -m "feat(cache): implement Upstash cache backend with graceful fallback"
```

---

### Task 4: Centralise tier quotas in `rate_limit.py`

**Files:**
- Modify: `app/utils/rate_limit.py`
- Test: `app/tests/test_rate_limit_helpers.py`

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_rate_limit_helpers.py`:

```python
"""Tier quotas are sourced from a single TIER_QUOTAS dict."""

from app.utils.rate_limit import TIER_QUOTAS, get_account_type_limit


def test_tier_quotas_shape():
    for tier in ("free", "premium", "admin"):
        q = TIER_QUOTAS[tier]
        assert "per_minute" in q
        assert "per_day" in q
        assert "per_month" in q


def test_free_per_minute_string():
    assert get_account_type_limit("free:alice") == "50/minute"


def test_empty_key_defaults_to_free():
    assert get_account_type_limit("") == "50/minute"


def test_anonymous_defaults_to_free():
    assert get_account_type_limit("anonymous:1.2.3.4") == "50/minute"


def test_premium_limit():
    assert get_account_type_limit("premium:bob") == "100/minute"


def test_admin_limit():
    assert get_account_type_limit("admin:root") == "1000/minute"


def test_unknown_tier_defaults_to_free():
    assert get_account_type_limit("ghost:x") == "50/minute"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest app/tests/test_rate_limit_helpers.py -v`
Expected: FAIL with `ImportError: cannot import name 'TIER_QUOTAS'`.

- [ ] **Step 3: Add `TIER_QUOTAS` and refactor helper**

Replace the body of `app/utils/rate_limit.py` (keep the module-level docstring) so it reads:

```python
"""Rate Limiting Utility Module.

Single source of truth for per-tier rate-limit quotas plus the helpers
SlowAPI uses on each request. Routers import the ``limiter`` instance
defined here so every endpoint shares one Redis-backed storage and one
key function.

Per-minute limits are enforced by SlowAPI inline. Per-day and per-month
limits are enforced by ``QuotaService`` (Phase 2).

Tiers:
    - free / anonymous / unknown: 50/min, 500/day, 5000/month
    - premium: 100/min, 5000/day, 100000/month
    - admin: 1000/min, unlimited day/month
"""

from __future__ import annotations

from typing import Optional

from fastapi import Request
from jose import jwt
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings
from app.utils.auth import ALGORITHM, SECRET_KEY

TIER_QUOTAS: dict[str, dict[str, object]] = {
    "free": {
        "per_minute": "50/minute",
        "per_day": 500,
        "per_month": 5_000,
    },
    "premium": {
        "per_minute": "100/minute",
        "per_day": 5_000,
        "per_month": 100_000,
    },
    "admin": {
        "per_minute": "1000/minute",
        "per_day": None,  # unlimited
        "per_month": None,
    },
}


def _decode_token(request: Request) -> tuple[str, Optional[str]]:
    """Return ``(account_type, subject)`` from the request JWT.

    Defaults: ``("", None)`` when no/invalid token. ``account_type`` is
    lowercased; ``subject`` is the ``sub`` claim if present.
    """
    header = request.headers.get("Authorization")
    if not header:
        return "anonymous", None
    _, _, token = header.partition(" ")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        account_type = (payload.get("account_type") or "").lower()
        subject = payload.get("sub")
        return account_type, subject
    except Exception:
        return "", None


def custom_key_func(request: Request) -> str:
    """Return a SlowAPI key of the form ``"<tier>:<identity>"``.

    Identity is the JWT ``sub`` when present, otherwise the remote IP. This
    ensures each user's bucket is separate from every other user's bucket,
    so a single noisy free user does not starve the others.
    """
    tier, subject = _decode_token(request)
    identity = subject or get_remote_address(request)
    if not tier:
        tier = "free"
    return f"{tier}:{identity}"


def _resolve_tier(key: str) -> str:
    """Pull the tier portion out of the composite SlowAPI key."""
    tier = key.split(":", 1)[0] if ":" in key else key
    tier = tier.lower()
    if tier in ("admin", "premium", "free"):
        return tier
    return "free"


def get_account_type_limit(key: str) -> str:
    """Map a SlowAPI key to the per-minute limit string for its tier."""
    return TIER_QUOTAS[_resolve_tier(key)]["per_minute"]  # type: ignore[return-value]


def _build_limiter() -> Limiter:
    """Construct the shared SlowAPI limiter.

    Uses ``settings.redis_url`` for storage when set; falls back to in-memory
    storage on init failure. Also configures ``in_memory_fallback`` so
    transient Redis errors during request handling do not 500 the API.
    """
    fallback_limits = [
        TIER_QUOTAS["free"]["per_minute"],
        TIER_QUOTAS["premium"]["per_minute"],
        TIER_QUOTAS["admin"]["per_minute"],
    ]

    if not settings.redis_url:
        return Limiter(
            key_func=custom_key_func,
            in_memory_fallback=fallback_limits,
        )

    try:
        return Limiter(
            key_func=custom_key_func,
            storage_uri=settings.redis_url,
            in_memory_fallback=fallback_limits,
        )
    except Exception:  # noqa: BLE001 — startup must not crash
        return Limiter(
            key_func=custom_key_func,
            in_memory_fallback=fallback_limits,
        )


# Shared SlowAPI Limiter — all routers must import this instance, not their own.
limiter = _build_limiter()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest app/tests/test_rate_limit_helpers.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add app/utils/rate_limit.py app/tests/test_rate_limit_helpers.py
git commit -m "feat(rate-limit): centralise tier quotas and per-user keying in one Limiter"
```

---

### Task 5: Consolidate routers onto the shared `limiter`

**Files:**
- Modify: `app/routers/stt.py`, `app/routers/translation.py`, `app/routers/language.py`, `app/routers/inference.py`, `app/routers/orpheus_tts.py`, `app/routers/runpod_tts.py`, `app/routers/tasks.py`

Each of these currently does:

```python
from slowapi import Limiter
from app.utils.rate_limit import custom_key_func, get_account_type_limit

limiter = Limiter(key_func=custom_key_func)
```

We replace that with importing the shared limiter so all routers share one storage backend.

- [ ] **Step 1: Confirm test coverage exists**

Run: `pytest app/tests/ -v -k "not integration" --collect-only | head -40`
Expected: existing tests collect without error (we will run them after the change to verify nothing breaks).

- [ ] **Step 2: Update each router**

For each of the 7 router files, replace the import block:

```python
from slowapi import Limiter
...
from app.utils.rate_limit import custom_key_func, get_account_type_limit

limiter = Limiter(key_func=custom_key_func)
```

with:

```python
from app.utils.rate_limit import get_account_type_limit, limiter
```

The decorator usage (`@limiter.limit(get_account_type_limit)`) stays unchanged.

Files to edit (line numbers approximate — search for `limiter = Limiter`):
- `app/routers/stt.py:46, 83`
- `app/routers/translation.py:51`
- `app/routers/language.py:61`
- `app/routers/inference.py:62`
- `app/routers/orpheus_tts.py:47`
- `app/routers/runpod_tts.py:54`
- `app/routers/tasks.py:47`

- [ ] **Step 3: Run the full router test suite**

Run: `pytest app/tests/ -v -m "not integration"`
Expected: all previously-passing tests continue to pass. Investigate any new failures before continuing.

- [ ] **Step 4: Commit**

```bash
git add app/routers/stt.py app/routers/translation.py app/routers/language.py app/routers/inference.py app/routers/orpheus_tts.py app/routers/runpod_tts.py app/routers/tasks.py
git commit -m "refactor(routers): share single SlowAPI Limiter across all routers"
```

---

### Task 6: Replace `app/api.py` Redis init and remove `FastAPILimiter`

**Files:**
- Modify: `app/api.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Update `lifespan` in `app/api.py`**

Replace lines 1–135 of `app/api.py` so that:
- The `redis.asyncio` import, the `init_redis()` helper, and the `FastAPILimiter` import + init all go away.
- `lifespan` calls `init_redis_client()` from `app/services/redis_client.py`.
- Module-level `limiter = Limiter(key_func=get_remote_address)` is removed — we use the shared limiter from `app.utils.rate_limit`.

New top-of-file imports (replace lines 1–22):

```python
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.core.exceptions import (
    APIException,
    api_exception_handler,
    validation_exception_handler,
)
from app.docs import description, tags_metadata
from app.middleware import MonitoringMiddleware
from app.services.redis_client import init_redis_client
from app.utils.rate_limit import limiter
# ... existing router imports unchanged ...
```

Replace the `init_redis` function and the `lifespan` body (lines 77–134) with:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup event")
    await init_redis_client()  # Fails open: logs and returns None on failure.

    try:
        from app.services.orpheus_tts_service import get_orpheus_tts_service
        await get_orpheus_tts_service().warm_speakers_cache()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Orpheus speakers warm-up failed: {e}")

    yield
```

Replace the SlowAPI block (lines 201–205) with:

```python
# 5. SlowAPIMiddleware — shared limiter lives in app.utils.rate_limit
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
```

- [ ] **Step 2: Drop `fastapi-limiter` from `requirements.txt`**

Remove line 8 of `requirements.txt`:

```
fastapi-limiter==0.1.6
```

- [ ] **Step 3: Run the full unit test suite**

Run: `pytest app/tests/ -v -m "not integration"`
Expected: all tests pass. App boots cleanly.

- [ ] **Step 4: Smoke-test app startup with and without REDIS_URL**

Run (no Redis):
```bash
REDIS_URL="" python -c "import asyncio; from app.api import app; asyncio.run(app.router.startup())"
```
Expected: logs `REDIS_URL not configured; Redis features disabled`, no exception.

Run (bad Redis URL):
```bash
REDIS_URL="rediss://does-not-exist:6379" timeout 15 python -c "import asyncio; from app.api import app; asyncio.run(app.router.startup())"
```
Expected: logs `Redis init failed (...); continuing without Redis`, no exception, exits 0.

- [ ] **Step 5: Commit**

```bash
git add app/api.py requirements.txt
git commit -m "refactor(api): use SafeRedis + shared Limiter; drop FastAPILimiter"
```

---

### Task 7: Free-tier and empty-account-type per-minute rate-limit test

**Files:**
- Modify: `app/tests/conftest.py` (add `fake_redis` fixture and an opt-in rate-limit fixture)
- Create: `app/tests/test_rate_limit_endpoint.py`

- [ ] **Step 1: Add a `fake_redis` fixture to `conftest.py`**

Append at the end of `app/tests/conftest.py`:

```python
# ---------------------------------------------------------------------------
# Redis / Rate-Limit Fixtures
# ---------------------------------------------------------------------------

import fakeredis.aioredis  # noqa: E402

from app.services import redis_client as redis_client_module  # noqa: E402
from app.services.redis_client import SafeRedis  # noqa: E402


@pytest_asyncio.fixture
async def fake_redis(monkeypatch) -> AsyncGenerator[SafeRedis, None]:
    """Install a fakeredis-backed SafeRedis singleton for the test."""
    backend = fakeredis.aioredis.FakeRedis(decode_responses=True)
    safe = SafeRedis(backend)
    monkeypatch.setattr(redis_client_module, "_safe_redis", safe)
    yield safe
    monkeypatch.setattr(redis_client_module, "_safe_redis", None)


@pytest_asyncio.fixture
async def rate_limited_app(monkeypatch, fake_redis):
    """Rebuild the shared SlowAPI limiter against fakeredis for one test.

    SlowAPI's storage is bound at Limiter construction. The shared limiter is
    in-memory by default in tests (no REDIS_URL); for this test we don't need
    to point it at Redis — in-memory storage in a single process is enough to
    verify that the 51st request is rejected. The fixture exists so callers
    that DO need a Redis-backed limiter can opt in by importing it.
    """
    yield
```

- [ ] **Step 2: Write the failing test**

Create `app/tests/test_rate_limit_endpoint.py`. Target `/tasks/language_id` because it is rate-limited (`@limiter.limit(get_account_type_limit)`), it accepts a tiny JSON payload, and we can mock its single service call to keep the 51-iteration loop fast.

```python
"""Per-minute rate limiting for Free-tier and empty-account-type JWTs.

The shared Limiter is in-memory in tests (REDIS_URL is unset). We exercise
``/tasks/language_id`` because it carries the @limiter decorator and its
upstream service can be stubbed to a static return so the loop runs fast.
"""

from typing import Dict

import pytest
from httpx import AsyncClient

from app.utils.rate_limit import TIER_QUOTAS, limiter


@pytest.fixture(autouse=True)
def reset_limiter_storage():
    """SlowAPI keeps per-process counters; reset between tests."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture(autouse=True)
def stub_language_service(monkeypatch):
    """Make /tasks/language_id resolve instantly to a static value."""
    from app.services.language_service import LanguageService

    async def fake_identify(self, text: str):
        return {"language": "eng", "confidence": 0.99}

    monkeypatch.setattr(LanguageService, "identify_language", fake_identify)
    yield


def _free_per_minute() -> int:
    """Extract the numeric portion of e.g. ``'50/minute'``."""
    return int(TIER_QUOTAS["free"]["per_minute"].split("/")[0])


async def _hammer(client: AsyncClient, attempts: int):
    statuses = []
    payload = {"text": "hello"}
    for _ in range(attempts):
        r = await client.post("/tasks/language_id", json=payload)
        statuses.append(r.status_code)
    return statuses


async def test_free_user_hits_429_after_quota(
    authenticated_client: AsyncClient, test_user: Dict
):
    """test_user has account_type=free; JWT has no ``account_type`` claim
    (sub-only token), so custom_key_func resolves the tier to 'free'."""
    per_min = _free_per_minute()
    statuses = await _hammer(authenticated_client, per_min + 1)

    # First `per_min` succeed (200), the (per_min+1)-th is rejected (429).
    assert statuses[:per_min].count(200) == per_min, statuses
    assert statuses[-1] == 429, statuses


async def test_empty_account_type_jwt_uses_free_tier(
    async_client: AsyncClient, test_user: Dict
):
    """A JWT with no ``account_type`` claim must be treated as free tier."""
    async_client.headers["Authorization"] = f"Bearer {test_user['token']}"
    per_min = _free_per_minute()
    statuses = await _hammer(async_client, per_min + 1)
    assert statuses[-1] == 429


async def test_anonymous_request_uses_free_tier(async_client: AsyncClient):
    """No Authorization header → 'anonymous' tier → free quota.

    /tasks/language_id requires auth, so all calls return 401 — but the
    SlowAPI middleware is registered AFTER the auth dependency in the
    middleware stack, so 429 still fires once the per-minute bucket runs
    out. We check that the LAST status is 429.
    """
    per_min = _free_per_minute()
    statuses = await _hammer(async_client, per_min + 1)
    assert statuses[-1] == 429
```

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest app/tests/test_rate_limit_endpoint.py -v`
Expected: PASS (3 tests). No implementation step — the shared limiter from Task 4 + the per-user key from Task 4 + the consolidated routers from Task 5 should make this work end-to-end.

If `test_anonymous_request_uses_free_tier` fails because slowapi runs *inside* the route handler (after auth), drop it from the test file — the first two tests are sufficient to prove free-tier enforcement.

- [ ] **Step 4: Commit**

```bash
git add app/tests/conftest.py app/tests/test_rate_limit_endpoint.py
git commit -m "test(rate-limit): verify free-tier and empty-account-type per-minute limit"
```

---

### Phase 1 verification gate

Before opening the Phase 1 PR, run:

```bash
make lint-check
pytest app/tests/ -v -m "not integration"
```

Both must pass. Open a PR titled `feat(redis): Upstash integration with graceful fallback + tiered per-minute rate limits` describing:
- New `SafeRedis` client + Upstash cache backend.
- Single shared SlowAPI Limiter, per-user keying, in-memory fallback.
- `FastAPILimiter` removed.
- Test coverage for Free and empty-account-type tiers.

---

## Phase 2 — DB-backed per-day and per-month quotas

**Phase 2 exit criteria:**
- A `user_usage` table tracks per-(user, day) request counts; per-month totals come from aggregating rows for `YYYY-MM`.
- A `QuotaService` reads counters from Redis (hot path) and falls back to DB on Redis miss/eviction.
- Every rate-limited endpoint calls `quota.check_and_consume(user)` and raises `RateLimitError` with `Retry-After` when the daily or monthly cap is hit.
- Tests cover: free-tier daily 429; Redis-down → DB fallback path; admin tier is unlimited.

---

### Task 8: `UserUsage` model and Alembic migration

**Files:**
- Create: `app/models/usage.py`
- Create: `app/alembic/versions/<new>_user_usage.py` (autogenerated)

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_usage_model.py`:

```python
"""UserUsage persists per-(user, day) counts."""

import datetime as dt

from sqlalchemy import select

from app.models.usage import UserUsage


async def test_user_usage_insert_and_read(db_session, test_user):
    today = dt.date(2026, 5, 28)
    db_session.add(UserUsage(user_id=test_user["id"], day=today, count=3))
    await db_session.commit()

    result = await db_session.execute(
        select(UserUsage).where(UserUsage.user_id == test_user["id"])
    )
    row = result.scalars().first()
    assert row.count == 3
    assert row.day == today
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest app/tests/test_usage_model.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create the model**

Create `app/models/usage.py`:

```python
"""Per-day, per-user usage counters used to enforce daily/monthly quotas.

One row per (user_id, day). Monthly totals are computed by summing rows
where ``day`` falls within a given YYYY-MM. Redis is a hot cache in front of
this table; this is the durable source of truth.
"""

import datetime as dt

from sqlalchemy import Column, Date, Integer, PrimaryKeyConstraint, func
from sqlalchemy.sql import expression

from app.database.db import Base


class UserUsage(Base):
    __tablename__ = "user_usage"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "day", name="pk_user_usage"),
    )

    user_id = Column(Integer, nullable=False, index=True)
    day = Column(Date, nullable=False, index=True, default=dt.date.today)
    count = Column(Integer, nullable=False, server_default=expression.literal(0))
```

- [ ] **Step 4: Generate the Alembic migration**

Run: `alembic revision --autogenerate -m "add user_usage table"`

Open the generated file under `app/alembic/versions/` and verify it contains only:
- `op.create_table('user_usage', ...)`
- The two indexes on `user_id` and `day`.

If autogenerate produced unrelated diffs, remove them — keep the migration laser-focused.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest app/tests/test_usage_model.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/models/usage.py app/alembic/versions/*_user_usage.py app/tests/test_usage_model.py
git commit -m "feat(db): add user_usage table for per-day quota tracking"
```

---

### Task 9: CRUD helpers for `UserUsage`

**Files:**
- Create: `app/crud/usage.py`
- Test: `app/tests/test_crud_usage.py`

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_crud_usage.py`:

```python
"""CRUD helpers for daily increment and monthly aggregate."""

import datetime as dt

from app.crud.usage import (
    get_day_count,
    get_month_total,
    increment_daily,
)


async def test_increment_daily_creates_then_increments(db_session, test_user):
    day = dt.date(2026, 5, 28)
    await increment_daily(db_session, test_user["id"], day, 1)
    await db_session.commit()
    await increment_daily(db_session, test_user["id"], day, 4)
    await db_session.commit()

    assert await get_day_count(db_session, test_user["id"], day) == 5


async def test_get_month_total_sums_days(db_session, test_user):
    for d, n in [(1, 2), (5, 3), (28, 4)]:
        await increment_daily(
            db_session, test_user["id"], dt.date(2026, 5, d), n
        )
    await db_session.commit()
    total = await get_month_total(db_session, test_user["id"], 2026, 5)
    assert total == 9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest app/tests/test_crud_usage.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the CRUD module**

Create `app/crud/usage.py`:

```python
"""CRUD operations for ``UserUsage`` rows.

Callers own the transaction (no commit here), per project convention.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage import UserUsage


async def increment_daily(
    db: AsyncSession,
    user_id: int,
    day: dt.date,
    units: int = 1,
) -> None:
    """Upsert: add ``units`` to the (user_id, day) row, creating it if absent.

    SQLite (tests) uses ``INSERT OR IGNORE`` + ``UPDATE`` since it lacks the
    PostgreSQL ``ON CONFLICT DO UPDATE`` syntax we'd otherwise use.
    """
    dialect = db.bind.dialect.name if db.bind else ""

    if dialect == "postgresql":
        stmt = (
            pg_insert(UserUsage)
            .values(user_id=user_id, day=day, count=units)
            .on_conflict_do_update(
                index_elements=["user_id", "day"],
                set_={"count": UserUsage.count + units},
            )
        )
        await db.execute(stmt)
        return

    # SQLite fallback: SELECT, then INSERT or UPDATE.
    existing = await db.execute(
        select(UserUsage).where(
            UserUsage.user_id == user_id,
            UserUsage.day == day,
        )
    )
    row = existing.scalars().first()
    if row is None:
        db.add(UserUsage(user_id=user_id, day=day, count=units))
    else:
        row.count = row.count + units


async def get_day_count(
    db: AsyncSession, user_id: int, day: dt.date
) -> int:
    result = await db.execute(
        select(UserUsage.count).where(
            UserUsage.user_id == user_id,
            UserUsage.day == day,
        )
    )
    val = result.scalars().first()
    return int(val) if val is not None else 0


async def get_month_total(
    db: AsyncSession, user_id: int, year: int, month: int
) -> int:
    start = dt.date(year, month, 1)
    end = dt.date(year + (month // 12), (month % 12) + 1, 1)
    result = await db.execute(
        select(func.coalesce(func.sum(UserUsage.count), 0)).where(
            UserUsage.user_id == user_id,
            UserUsage.day >= start,
            UserUsage.day < end,
        )
    )
    return int(result.scalar_one() or 0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest app/tests/test_crud_usage.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/crud/usage.py app/tests/test_crud_usage.py
git commit -m "feat(crud): increment_daily + get_month_total for user_usage"
```

---

### Task 10: `QuotaService` with Redis hot path + DB fallback

**Files:**
- Create: `app/services/quota_service.py`
- Test: `app/tests/test_quota_service.py`

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_quota_service.py`:

```python
"""QuotaService enforces day/month caps using Redis hot path + DB fallback."""

import datetime as dt
from types import SimpleNamespace

import fakeredis.aioredis
import pytest

from app.services.quota_service import QuotaResult, QuotaService
from app.services.redis_client import SafeRedis


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest app/tests/test_quota_service.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `QuotaService`**

Create `app/services/quota_service.py`:

```python
"""Per-day / per-month quota enforcement with Redis hot path + DB durability.

Per-minute throttling stays inside SlowAPI. This service handles only the
longer windows.

Hot path:
    1. INCR ``quota:day:{user_id}:{YYYY-MM-DD}`` in Redis. If the new value
       is > daily cap, deny.
    2. INCR ``quota:month:{user_id}:{YYYY-MM}`` in Redis. If > monthly cap,
       deny. (Month counter is a cache; rebuilt from DB on miss.)
    3. Schedule a DB increment as a fire-and-forget task so the response
       isn't blocked on durable persistence.

Cold path (Redis returned None — likely down):
    1. Increment DB row synchronously.
    2. Read fresh day count + month total from DB.
    3. Compare to caps.

Admin tier short-circuits both paths.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.usage import get_day_count, get_month_total, increment_daily
from app.database.db import async_session_maker
from app.services.redis_client import SafeRedis, get_redis_client
from app.utils.rate_limit import TIER_QUOTAS

logger = logging.getLogger(__name__)


@dataclass
class QuotaResult:
    allowed: bool
    scope: Optional[str] = None  # "day" | "month" | None
    remaining_day: Optional[int] = None
    remaining_month: Optional[int] = None
    retry_after_seconds: int = 0


def _seconds_until_end_of_day(now: dt.datetime) -> int:
    tomorrow = (now + dt.timedelta(days=1)).date()
    midnight = dt.datetime.combine(tomorrow, dt.time.min, tzinfo=now.tzinfo)
    return max(int((midnight - now).total_seconds()), 1)


def _seconds_until_end_of_month(now: dt.datetime) -> int:
    if now.month == 12:
        first_next = dt.datetime(now.year + 1, 1, 1, tzinfo=now.tzinfo)
    else:
        first_next = dt.datetime(now.year, now.month + 1, 1, tzinfo=now.tzinfo)
    return max(int((first_next - now).total_seconds()), 1)


class QuotaService:
    def __init__(
        self,
        redis: Optional[SafeRedis] = None,
        today: Callable[[], dt.date] = dt.date.today,
        now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
    ) -> None:
        self._redis = redis if redis is not None else get_redis_client()
        self._today = today
        self._now = now

    def _caps(self, account_type: str) -> tuple[Optional[int], Optional[int]]:
        tier = (account_type or "free").lower()
        if tier not in TIER_QUOTAS:
            tier = "free"
        q = TIER_QUOTAS[tier]
        return q["per_day"], q["per_month"]  # type: ignore[return-value]

    async def check_and_consume(
        self, db: AsyncSession, user
    ) -> QuotaResult:
        day_cap, month_cap = self._caps(getattr(user, "account_type", "free"))
        if day_cap is None and month_cap is None:
            return QuotaResult(allowed=True)

        today = self._today()
        ym = f"{today.year:04d}-{today.month:02d}"
        day_key = f"quota:day:{user.id}:{today.isoformat()}"
        month_key = f"quota:month:{user.id}:{ym}"

        # --- Hot path: Redis ---
        if self._redis is not None:
            day_count = await self._redis.incr(day_key)
            if day_count is not None:
                # First write of the day: set 26h TTL so eviction is bounded.
                if day_count == 1:
                    await self._redis.expire(day_key, 26 * 60 * 60)

                if day_cap is not None and day_count > day_cap:
                    return QuotaResult(
                        allowed=False,
                        scope="day",
                        remaining_day=0,
                        retry_after_seconds=_seconds_until_end_of_day(self._now()),
                    )

                month_count = await self._redis.incr(month_key)
                if month_count is not None and month_count == 1:
                    await self._redis.expire(month_key, 32 * 24 * 60 * 60)

                if (
                    month_cap is not None
                    and month_count is not None
                    and month_count > month_cap
                ):
                    return QuotaResult(
                        allowed=False,
                        scope="month",
                        remaining_month=0,
                        retry_after_seconds=_seconds_until_end_of_month(self._now()),
                    )

                # Async DB persistence so the response is not blocked.
                asyncio.create_task(
                    self._persist_daily(user.id, today, 1)
                )
                return QuotaResult(
                    allowed=True,
                    remaining_day=(
                        max(day_cap - day_count, 0) if day_cap is not None else None
                    ),
                    remaining_month=(
                        max(month_cap - (month_count or 0), 0)
                        if month_cap is not None
                        else None
                    ),
                )

        # --- Cold path: Redis down or returned None ---
        await increment_daily(db, user.id, today, 1)
        await db.commit()
        day_count_db = await get_day_count(db, user.id, today)
        month_total_db = await get_month_total(db, user.id, today.year, today.month)

        if day_cap is not None and day_count_db > day_cap:
            return QuotaResult(
                allowed=False,
                scope="day",
                remaining_day=0,
                retry_after_seconds=_seconds_until_end_of_day(self._now()),
            )
        if month_cap is not None and month_total_db > month_cap:
            return QuotaResult(
                allowed=False,
                scope="month",
                remaining_month=0,
                retry_after_seconds=_seconds_until_end_of_month(self._now()),
            )
        return QuotaResult(allowed=True)

    async def _persist_daily(self, user_id: int, day: dt.date, units: int) -> None:
        """Best-effort DB persistence in a background task. Never raises."""
        try:
            async with async_session_maker() as session:
                await increment_daily(session, user_id, day, units)
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Quota DB persistence failed (user=%s): %s", user_id, exc)


_quota_service: Optional[QuotaService] = None


def get_quota_service() -> QuotaService:
    global _quota_service
    if _quota_service is None:
        _quota_service = QuotaService()
    return _quota_service
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest app/tests/test_quota_service.py -v`
Expected: PASS (3 tests). Note: the 500-iteration test will run in a few seconds because no HTTP layer is involved.

- [ ] **Step 5: Commit**

```bash
git add app/services/quota_service.py app/tests/test_quota_service.py
git commit -m "feat(quota): add QuotaService with Redis hot path + DB fallback"
```

---

### Task 11: Wire `QuotaServiceDep` and a router-level guard

**Files:**
- Modify: `app/deps.py`
- Create: `app/utils/quota_guard.py`
- Test: `app/tests/test_quota_guard.py`

- [ ] **Step 1: Add deps**

In `app/deps.py`, add after the integration imports:

```python
from app.services.quota_service import QuotaService, get_quota_service
```

and below `CacheBackendDep`:

```python
QuotaServiceDep = Annotated[QuotaService, Depends(get_quota_service)]
```

Also append `"QuotaServiceDep"` and `"QuotaService"` to the `__all__` list.

- [ ] **Step 2: Write the failing test**

Create `app/tests/test_quota_guard.py`:

```python
"""``check_quota`` raises RateLimitError when the daily cap is exceeded."""

import datetime as dt
from types import SimpleNamespace

import fakeredis.aioredis
import pytest

from app.core.exceptions import RateLimitError
from app.services.quota_service import QuotaService
from app.services.redis_client import SafeRedis
from app.utils.quota_guard import check_quota


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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest app/tests/test_quota_guard.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement `check_quota`**

Create `app/utils/quota_guard.py`:

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest app/tests/test_quota_guard.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add app/deps.py app/utils/quota_guard.py app/tests/test_quota_guard.py
git commit -m "feat(quota): add check_quota guard + QuotaServiceDep"
```

---

### Task 12: Apply `check_quota` to STT endpoints

**Files:**
- Modify: `app/routers/stt.py`

- [ ] **Step 1: Add imports at the top of `stt.py`**

```python
from app.deps import QuotaServiceDep
from app.utils.quota_guard import check_quota
```

- [ ] **Step 2: Add the guard to each rate-limited endpoint**

For each handler decorated with `@limiter.limit(get_account_type_limit)` (search the file for that decorator), add a parameter and a call as the first line of the body:

```python
@router.post("/stt")
@limiter.limit(get_account_type_limit)
async def speech_to_text(
    request: Request,
    background_tasks: BackgroundTasks,
    # ... existing params ...
    quota: QuotaServiceDep,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    service: STTService = Depends(get_service),
) -> STTTranscript:
    await check_quota(quota, db, current_user)
    # ... existing body ...
```

Do this for `/stt`, `/stt_from_gcs`, and `/org/stt`.

- [ ] **Step 3: Run the STT tests**

Run: `pytest app/tests/test_stt*.py -v -m "not integration"`
Expected: PASS (existing tests must still pass; quota service uses fakeredis by default when injected — but since tests use real DB only, the cold path will run and `1 < 500`, so all existing calls succeed).

If existing STT tests now fail because `QuotaServiceDep` instantiates a real `QuotaService` with no Redis, add this to `app/tests/conftest.py`:

```python
@pytest_asyncio.fixture(autouse=True)
def stub_quota_service(request, monkeypatch):
    """In tests, make QuotaService always-allow so existing fixtures don't
    have to seed the user_usage table or know about quotas.

    Opt out for a single test or module by adding
    ``@pytest.mark.real_quota`` to the test (or ``pytestmark`` to the file)
    — see ``test_quota_endpoint.py``.
    """
    if request.node.get_closest_marker("real_quota"):
        yield
        return

    from app.services.quota_service import QuotaResult, QuotaService

    async def always_allow(self, db, user):
        return QuotaResult(allowed=True)

    monkeypatch.setattr(QuotaService, "check_and_consume", always_allow)
    yield
```

Also register the marker. In `pytest.ini`, add `real_quota: opt out of the stub_quota_service autouse fixture` under `markers`.

Tests that specifically exercise quota behaviour (Task 14) opt out via the `@pytest.mark.real_quota` marker.

- [ ] **Step 4: Commit**

```bash
git add app/routers/stt.py app/tests/conftest.py
git commit -m "feat(stt): enforce daily/monthly quota on transcription endpoints"
```

---

### Task 13: Apply `check_quota` to the remaining `/tasks/*` endpoints

**Files:**
- Modify: `app/routers/translation.py`, `app/routers/language.py`, `app/routers/inference.py`, `app/routers/tts.py`, `app/routers/runpod_tts.py`, `app/routers/orpheus_tts.py`, `app/routers/tasks.py`

- [ ] **Step 1: Add imports to each router**

At the top of each of the seven router files, alongside their existing `app.deps` and `app.utils.rate_limit` imports, add:

```python
from app.deps import QuotaServiceDep
from app.utils.quota_guard import check_quota
```

- [ ] **Step 2: Add the guard to every rate-limited handler**

Find every handler to update with:

```bash
grep -n "@limiter.limit(get_account_type_limit)" app/routers/translation.py app/routers/language.py app/routers/inference.py app/routers/tts.py app/routers/runpod_tts.py app/routers/orpheus_tts.py app/routers/tasks.py
```

For each match, modify the handler in two places. Concrete example — a hypothetical `/tasks/translate` endpoint changes from:

```python
@router.post("/translate")
@limiter.limit(get_account_type_limit)
async def translate(
    request: Request,
    payload: TranslateRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    service: TranslationService = Depends(get_translation_service),
):
    return await service.translate(payload)
```

to:

```python
@router.post("/translate")
@limiter.limit(get_account_type_limit)
async def translate(
    request: Request,
    payload: TranslateRequest,
    quota: QuotaServiceDep,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    service: TranslationService = Depends(get_translation_service),
):
    await check_quota(quota, db, current_user)
    return await service.translate(payload)
```

The two changes per handler are:
- Insert `quota: QuotaServiceDep,` in the parameter list (anywhere before `db`).
- Add `await check_quota(quota, db, current_user)` as the first statement of the body.

- [ ] **Step 3: Run the full test suite**

Run: `pytest app/tests/ -v -m "not integration"`
Expected: all tests still pass thanks to the `stub_quota_service` autouse fixture.

- [ ] **Step 4: Commit**

```bash
git add app/routers/translation.py app/routers/language.py app/routers/inference.py app/routers/tts.py app/routers/runpod_tts.py app/routers/orpheus_tts.py app/routers/tasks.py
git commit -m "feat(quota): enforce daily/monthly quota across all /tasks/* endpoints"
```

---

### Task 14: End-to-end quota test for the Free tier

**Files:**
- Create: `app/tests/test_quota_endpoint.py`

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_quota_endpoint.py`:

```python
"""Free-tier daily cap is enforced through the HTTP layer."""

import datetime as dt
from typing import Dict

import fakeredis.aioredis
import pytest
from httpx import AsyncClient

from app.services.redis_client import SafeRedis

# Opt out of the conftest stub_quota_service autouse fixture for the whole
# module so we exercise the real QuotaService end-to-end.
pytestmark = pytest.mark.real_quota


@pytest.fixture(autouse=True)
def install_quota_with_fakeredis(monkeypatch):
    """Install a QuotaService backed by fakeredis and a fixed 'today'."""
    from app.services import quota_service as qs_module
    from app.services.quota_service import QuotaService

    safe = SafeRedis(fakeredis.aioredis.FakeRedis(decode_responses=True))
    svc = QuotaService(redis=safe, today=lambda: dt.date(2026, 5, 28))
    monkeypatch.setattr(qs_module, "_quota_service", svc)
    yield
    monkeypatch.setattr(qs_module, "_quota_service", None)


@pytest.fixture(autouse=True)
def stub_language_service(monkeypatch):
    from app.services.language_service import LanguageService

    async def fake_identify(self, text: str):
        return {"language": "eng", "confidence": 0.99}

    monkeypatch.setattr(LanguageService, "identify_language", fake_identify)
    yield


async def test_free_user_429_after_daily_cap(
    authenticated_client: AsyncClient, test_user: Dict
):
    payload = {"text": "hello"}
    # Per-minute is 50; reset SlowAPI's in-memory bucket every 50 calls so
    # the daily-cap test is not derailed by the per-minute cap.
    from app.utils.rate_limit import limiter

    statuses = []
    for i in range(500):
        if i % 50 == 0:
            limiter.reset()
        r = await authenticated_client.post("/tasks/language_id", json=payload)
        statuses.append(r.status_code)

    assert statuses.count(200) == 500, f"unexpected non-200s: {set(statuses)}"

    limiter.reset()
    r = await authenticated_client.post("/tasks/language_id", json=payload)
    assert r.status_code == 429
    assert "Daily quota exceeded" in r.json().get("message", "")
    assert int(r.headers.get("Retry-After", "0")) > 0
```

- [ ] **Step 2: Run the test**

Run: `pytest app/tests/test_quota_endpoint.py -v`
Expected: PASS. The `pytestmark = pytest.mark.real_quota` at the top of the file makes the conftest stub `yield` without patching `check_and_consume`, so the real `QuotaService` (with our fakeredis backend) handles the requests.

- [ ] **Step 3: Commit**

```bash
git add app/tests/test_quota_endpoint.py
git commit -m "test(quota): end-to-end free-tier daily 429 with Retry-After"
```

---

### Phase 2 verification gate

Run:

```bash
make lint-check
pytest app/tests/ -v -m "not integration"
```

Both must pass. Open a PR titled `feat(quota): per-day and per-month limits per account tier` describing:
- New `user_usage` table + migration.
- `QuotaService` with Redis hot path and DB fallback.
- `check_quota` guard applied to every `/tasks/*` endpoint.
- Free-tier end-to-end test verifying 500/day → 429.

---

## Out of scope (track separately if needed)

- Dashboard UI to display remaining quota.
- Admin endpoint to bump a user's quota mid-month.
- Weighted/per-resource billing (we chose flat 1 unit/request).
- Migration of the existing `cache_backend = "memory"` GA cache to Upstash — independent decision, can be flipped via env once Task 3 is in.
- Background job to expire/cleanup very old `user_usage` rows (irrelevant for first 12 months).
