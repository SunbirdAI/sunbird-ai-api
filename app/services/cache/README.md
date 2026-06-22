# Cache Backend

This package provides a pluggable cache used by the Google Analytics
service (and future consumers). The default backend is in-memory and
scoped to a single Cloud Run instance; each replica keeps its own copy.

## Current backend

`InMemoryTTLCache` (in `in_memory.py`). Chosen because Redis/Memorystore
is expensive for admin-only traffic and our DB is hosted outside GCP.

## Migrating to Upstash (or any shared Redis)

When the cache needs to be shared across Cloud Run replicas, add a new
backend that satisfies the `CacheBackend` protocol and wire it up via
`CACHE_BACKEND=upstash`.

1. Install the client:

   ```
   pip install upstash-redis>=1.0.0
   ```

2. Add `app/services/cache/upstash.py`:

   ```python
   import json
   from upstash_redis.asyncio import Redis

   from app.core.config import settings


   class UpstashRedisCache:
       def __init__(self) -> None:
           self._client = Redis(
               url=settings.upstash_redis_rest_url,
               token=settings.upstash_redis_rest_token,
           )

       async def get(self, key: str):
           raw = await self._client.get(key)
           return json.loads(raw) if raw else None

       async def set(self, key: str, value, ttl_seconds: int) -> None:
           await self._client.set(key, json.dumps(value), ex=ttl_seconds)

       async def delete(self, key: str) -> None:
           await self._client.delete(key)
   ```

3. Add the two env vars to `Settings` in `app/core/config.py`:

   ```python
   upstash_redis_rest_url: Optional[str] = Field(default=None)
   upstash_redis_rest_token: Optional[str] = Field(default=None)
   ```

4. Update `get_cache_backend()` in `__init__.py`:

   ```python
   if settings.cache_backend == "upstash":
       from app.services.cache.upstash import UpstashRedisCache
       return UpstashRedisCache()
   ```

5. Set env vars in Cloud Run: `CACHE_BACKEND=upstash`,
   `UPSTASH_REDIS_REST_URL=...`, `UPSTASH_REDIS_REST_TOKEN=...`.

No other code changes. The service layer is unaware of the backend.
