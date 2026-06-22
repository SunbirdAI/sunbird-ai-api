# Google Analytics Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface GA4 analytics (traffic, content, platform, geography, events) for the Sunflower and Sunbird Speech properties on a new admin-only page at `/admin/google-analytics`.

**Architecture:** FastAPI router → GoogleAnalyticsService (orchestrates 5 reports, handles caching) → pluggable CacheBackend (in-memory today, Upstash later) → GoogleAnalyticsClient integration → Google Analytics Data API v1beta. Authentication uses short-lived impersonated service-account credentials from the Cloud Run identity (`379507182035-compute@developer.gserviceaccount.com`) targeting a dedicated `ga-reader@sb-gcp-project-01.iam.gserviceaccount.com` service account.

**Tech Stack:** Python 3.11, FastAPI, `google-analytics-data` SDK, `google.auth.impersonated_credentials`, pytest, React 18 + TypeScript + Vite, Chart.js, Tailwind CSS.

**Design spec:** [docs/superpowers/specs/2026-04-19-google-analytics-integration-design.md](../specs/2026-04-19-google-analytics-integration-design.md)

---

## Conventions for every task

- Write the test first, see it fail, then implement.
- Use project exception classes from `app/core/exceptions.py` (`BadRequestError`, `ExternalServiceError`, `AuthorizationError`) — never bare `HTTPException`.
- Inject services via `Annotated` aliases in `app/deps.py` — never import services directly into routers.
- Run `pytest app/tests/ -v` after every backend task; `npm run lint && npm run build` in `frontend/` after every frontend task.
- Commit after each task with a conventional message (`feat:`, `test:`, `docs:`, `chore:`).
- No emojis in code or commits unless the user asks.

---

## Task 1: Add dependencies and config fields

**Files:**
- Modify: `requirements.txt`
- Modify: `app/core/config.py`
- Test: `app/tests/test_config.py` (create if missing)

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_config.py` if it doesn't exist, otherwise append. The tests use `ga_properties_raw` (the field name) directly rather than the `GA_PROPERTIES` env-var alias, since pydantic-settings treats alias purely as the env-var source, not as a constructor kwarg:

```python
from app.core.config import Settings


def test_ga_properties_parses_env_string():
    s = Settings(
        ga_properties_raw="506611499:Sunflower,448469065:Sunbird Speech",
        ga_impersonation_target="ga-reader@test.iam.gserviceaccount.com",
    )
    assert s.ga_properties == {
        "506611499": "Sunflower",
        "448469065": "Sunbird Speech",
    }
    assert s.ga_enabled is True


def test_ga_enabled_false_when_no_target():
    s = Settings(ga_properties_raw="506611499:Sunflower")
    assert s.ga_enabled is False


def test_ga_enabled_false_when_no_properties():
    s = Settings(ga_impersonation_target="ga-reader@test.iam.gserviceaccount.com")
    assert s.ga_enabled is False


def test_ga_properties_ignores_malformed_entries():
    s = Settings(
        ga_properties_raw="506611499:Sunflower,malformed,448469065:Sunbird Speech"
    )
    assert s.ga_properties == {
        "506611499": "Sunflower",
        "448469065": "Sunbird Speech",
    }


def test_ga_properties_env_alias_works(monkeypatch):
    """End-to-end check: the GA_PROPERTIES alias populates ga_properties_raw."""
    monkeypatch.setenv("GA_PROPERTIES", "506611499:Sunflower")
    monkeypatch.setenv(
        "GA_IMPERSONATION_TARGET", "ga-reader@test.iam.gserviceaccount.com"
    )
    s = Settings()
    assert s.ga_properties == {"506611499": "Sunflower"}
    assert s.ga_enabled is True
```

- [ ] **Step 2: Run test to verify failure**

```
pytest app/tests/test_config.py -v
```
Expected: FAIL (attribute `ga_properties` does not exist on Settings).

- [ ] **Step 3: Edit `app/core/config.py`**

Add to the `Settings` class (near the end of the class body, before `@property is_production`):

```python
    # Google Analytics Data API
    ga_impersonation_target: Optional[str] = Field(
        default=None,
        description=(
            "Service account email to impersonate for the Google Analytics "
            "Data API (e.g. ga-reader@sb-gcp-project-01.iam.gserviceaccount.com)."
        ),
    )
    ga_properties_raw: str = Field(
        default="",
        alias="GA_PROPERTIES",
        description=(
            "Comma-separated `id:name` pairs, e.g. "
            "'506611499:Sunflower,448469065:Sunbird Speech'."
        ),
    )
    ga_cache_ttl_seconds: int = Field(
        default=3600, description="TTL for cached GA report payloads."
    )
    ga_request_timeout_seconds: int = Field(
        default=30, description="Timeout for a single GA Data API call."
    )
    cache_backend: str = Field(
        default="memory",
        description="Cache backend: 'memory' (default) or 'upstash'.",
    )
```

Add these properties next to `is_production`:

```python
    @property
    def ga_properties(self) -> dict[str, str]:
        """Parse GA_PROPERTIES env string into {property_id: display_name}."""
        result: dict[str, str] = {}
        for part in self.ga_properties_raw.split(","):
            part = part.strip()
            if ":" not in part:
                continue
            prop_id, name = part.split(":", 1)
            prop_id, name = prop_id.strip(), name.strip()
            if prop_id and name:
                result[prop_id] = name
        return result

    @property
    def ga_enabled(self) -> bool:
        """True iff both GA impersonation target and properties are configured."""
        return bool(self.ga_impersonation_target) and bool(self.ga_properties)
```

- [ ] **Step 4: Edit `requirements.txt`**

Append (maintain alphabetical order in the Google-libs section):

```
google-analytics-data>=0.18.0
```

(We deliberately do NOT add `cachetools` — the in-memory cache uses a plain dict for simplicity. See Task 2.)

- [ ] **Step 5: Install and re-run tests**

```
pip install -r requirements.txt
pytest app/tests/test_config.py -v
```
Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt app/core/config.py app/tests/test_config.py
git commit -m "feat(config): add Google Analytics settings and property parsing"
```

---

## Task 2: Cache protocol + in-memory implementation (TDD)

**Files:**
- Create: `app/services/cache/__init__.py`
- Create: `app/services/cache/in_memory.py`
- Create: `app/services/cache/README.md`
- Test: `app/tests/test_cache_in_memory.py`

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_cache_in_memory.py`:

```python
import asyncio

import pytest

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
    monkeypatch.setattr(
        "app.services.cache.in_memory.time.monotonic", lambda: now["t"]
    )
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
```

- [ ] **Step 2: Run test to verify failure**

```
pytest app/tests/test_cache_in_memory.py -v
```
Expected: FAIL (module does not exist).

- [ ] **Step 3: Create `app/services/cache/__init__.py`**

```python
"""Pluggable cache backend for short-lived server-side caches.

The default `InMemoryTTLCache` is per-Cloud Run instance. See
`README.md` in this directory for migrating to a shared Upstash Redis
backend.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CacheBackend(Protocol):
    """Async cache interface. Values must be JSON-serialisable."""

    async def get(self, key: str) -> Any | None: ...

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None: ...

    async def delete(self, key: str) -> None: ...
```

- [ ] **Step 4: Create `app/services/cache/in_memory.py`**

```python
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
```

- [ ] **Step 5: Run tests**

```
pytest app/tests/test_cache_in_memory.py -v
```
Expected: all 6 tests PASS.

- [ ] **Step 6: Create `app/services/cache/README.md`**

```markdown
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
```

- [ ] **Step 7: Commit**

```bash
git add app/services/cache app/tests/test_cache_in_memory.py
git commit -m "feat(cache): add pluggable cache backend with in-memory TTL default"
```

---

## Task 3: Cache factory + DI wiring

**Files:**
- Modify: `app/services/cache/__init__.py`
- Modify: `app/deps.py`
- Test: `app/tests/test_cache_factory.py`

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_cache_factory.py`:

```python
from app.services.cache import CacheBackend, get_cache_backend
from app.services.cache.in_memory import InMemoryTTLCache


def test_factory_returns_in_memory_by_default(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.cache_backend", "memory")
    # Clear singleton
    import app.services.cache as cache_mod
    cache_mod._instance = None

    backend = get_cache_backend()
    assert isinstance(backend, InMemoryTTLCache)
    assert isinstance(backend, CacheBackend)


def test_factory_returns_same_instance(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.cache_backend", "memory")
    import app.services.cache as cache_mod
    cache_mod._instance = None

    first = get_cache_backend()
    second = get_cache_backend()
    assert first is second


def test_factory_unknown_backend_raises(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.cache_backend", "bogus")
    import app.services.cache as cache_mod
    cache_mod._instance = None

    import pytest
    with pytest.raises(ValueError, match="Unknown cache_backend"):
        get_cache_backend()
```

- [ ] **Step 2: Run to verify failure**

```
pytest app/tests/test_cache_factory.py -v
```
Expected: FAIL (`get_cache_backend` not defined).

- [ ] **Step 3: Extend `app/services/cache/__init__.py`**

Append below the `CacheBackend` Protocol:

```python
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
```

- [ ] **Step 4: Wire DI in `app/deps.py`**

After the `StorageServiceDep` line (~line 69), add:

```python
from app.services.cache import CacheBackend, get_cache_backend
```

Near the other Annotated aliases:

```python
CacheBackendDep = Annotated[CacheBackend, Depends(get_cache_backend)]
```

Add `"CacheBackendDep"` and `"CacheBackend"` to `__all__`.

- [ ] **Step 5: Run tests**

```
pytest app/tests/test_cache_factory.py -v
```
Expected: all 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/cache/__init__.py app/deps.py app/tests/test_cache_factory.py
git commit -m "feat(cache): factory + DI wiring for cache backend"
```

---

## Task 4: GA integration client (with impersonation)

**Files:**
- Create: `app/integrations/google_analytics.py`
- Test: `app/tests/test_google_analytics_integration.py`

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_google_analytics_integration.py`:

```python
from unittest.mock import MagicMock, patch

import pytest

from app.integrations.google_analytics import GoogleAnalyticsClient


@pytest.fixture
def fake_ga_response():
    """Build a fake BetaAnalyticsDataClient.run_report response proto."""
    response = MagicMock()
    response.dimension_headers = [MagicMock(name="date")]
    response.dimension_headers[0].name = "date"
    response.metric_headers = [MagicMock(name="activeUsers")]
    response.metric_headers[0].name = "activeUsers"

    row = MagicMock()
    dim = MagicMock()
    dim.value = "2026-04-18"
    row.dimension_values = [dim]
    metric = MagicMock()
    metric.value = "42"
    row.metric_values = [metric]
    response.rows = [row]
    return response


async def test_run_report_returns_normalised_dict(fake_ga_response):
    with patch(
        "app.integrations.google_analytics.google.auth.default",
        return_value=(MagicMock(), None),
    ), patch(
        "app.integrations.google_analytics.impersonated_credentials.Credentials"
    ) as mock_creds, patch(
        "app.integrations.google_analytics.BetaAnalyticsDataClient"
    ) as mock_client_cls:
        mock_client = MagicMock()
        mock_client.run_report.return_value = fake_ga_response
        mock_client_cls.return_value = mock_client

        client = GoogleAnalyticsClient(target_sa="ga-reader@test.iam")
        result = await client.run_report(
            property_id="506611499",
            dimensions=["date"],
            metrics=["activeUsers"],
            start_date="7daysAgo",
        )

    assert result == {
        "dimension_headers": ["date"],
        "metric_headers": ["activeUsers"],
        "rows": [
            {"dimensions": ["2026-04-18"], "metrics": ["42"]},
        ],
    }
    mock_creds.assert_called_once()
    kwargs = mock_creds.call_args.kwargs
    assert kwargs["target_principal"] == "ga-reader@test.iam"
    assert kwargs["target_scopes"] == [
        "https://www.googleapis.com/auth/analytics.readonly"
    ]


async def test_run_report_passes_limit_and_order_bys():
    with patch(
        "app.integrations.google_analytics.google.auth.default",
        return_value=(MagicMock(), None),
    ), patch(
        "app.integrations.google_analytics.impersonated_credentials.Credentials"
    ), patch(
        "app.integrations.google_analytics.BetaAnalyticsDataClient"
    ) as mock_client_cls:
        mock_client = MagicMock()
        mock_client.run_report.return_value = MagicMock(
            dimension_headers=[], metric_headers=[], rows=[]
        )
        mock_client_cls.return_value = mock_client

        client = GoogleAnalyticsClient(target_sa="ga-reader@test.iam")
        await client.run_report(
            property_id="506611499",
            dimensions=["pagePath"],
            metrics=["screenPageViews"],
            start_date="7daysAgo",
            limit=10,
        )

    call_request = mock_client.run_report.call_args.args[0]
    assert call_request.property == "properties/506611499"
    assert call_request.limit == 10
```

- [ ] **Step 2: Run to verify failure**

```
pytest app/tests/test_google_analytics_integration.py -v
```
Expected: FAIL (module does not exist).

- [ ] **Step 3: Create `app/integrations/google_analytics.py`**

```python
"""Google Analytics Data API v1beta client with impersonated credentials.

This is a thin integration wrapper. It only handles auth setup and
proto-to-dict normalisation. All business logic lives in
`app/services/google_analytics_service.py`.
"""

import asyncio
import logging
from typing import Any

import google.auth
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Metric,
    OrderBy,
    RunReportRequest,
)
from google.auth import impersonated_credentials

logger = logging.getLogger(__name__)

GA_READ_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"


class GoogleAnalyticsClient:
    """Wraps `BetaAnalyticsDataClient` with impersonated credentials.

    The source credentials come from the Cloud Run runtime identity
    (or a developer's gcloud ADC locally). They are exchanged for
    short-lived credentials of `target_sa` every hour.
    """

    def __init__(self, target_sa: str, scopes: list[str] | None = None) -> None:
        self._target_sa = target_sa
        source_creds, _ = google.auth.default()
        self._creds = impersonated_credentials.Credentials(
            source_credentials=source_creds,
            target_principal=target_sa,
            target_scopes=scopes or [GA_READ_SCOPE],
            lifetime=3600,
        )
        self._client = BetaAnalyticsDataClient(credentials=self._creds)
        logger.info(
            "GoogleAnalyticsClient initialised (impersonating %s)", target_sa
        )

    async def run_report(
        self,
        property_id: str,
        dimensions: list[str],
        metrics: list[str],
        start_date: str,
        end_date: str = "today",
        limit: int | None = None,
        order_bys: list[OrderBy] | None = None,
    ) -> dict[str, Any]:
        """Execute a run_report call and return a plain-dict response.

        The underlying gRPC call is sync; we offload it to a thread so
        the FastAPI event loop stays responsive.
        """
        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=[Dimension(name=d) for d in dimensions],
            metrics=[Metric(name=m) for m in metrics],
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            limit=limit,
            order_bys=order_bys or [],
        )
        response = await asyncio.to_thread(self._client.run_report, request)
        return _response_to_dict(response)


def _response_to_dict(response: Any) -> dict[str, Any]:
    """Convert a RunReportResponse proto to a plain-dict shape."""
    return {
        "dimension_headers": [h.name for h in response.dimension_headers],
        "metric_headers": [h.name for h in response.metric_headers],
        "rows": [
            {
                "dimensions": [dv.value for dv in row.dimension_values],
                "metrics": [mv.value for mv in row.metric_values],
            }
            for row in response.rows
        ],
    }


_instance: GoogleAnalyticsClient | None = None


def get_google_analytics_client() -> GoogleAnalyticsClient:
    """Return a process-wide singleton client."""
    from app.core.config import settings

    global _instance
    if _instance is None:
        if not settings.ga_impersonation_target:
            raise RuntimeError(
                "GA_IMPERSONATION_TARGET is not configured. Set the env var "
                "or check `settings.ga_enabled` before constructing a client."
            )
        _instance = GoogleAnalyticsClient(
            target_sa=settings.ga_impersonation_target
        )
    return _instance
```

- [ ] **Step 4: Run tests**

```
pytest app/tests/test_google_analytics_integration.py -v
```
Expected: both tests PASS. If `google.analytics.data_v1beta` fails to import, the dependency from Task 1 wasn't installed — rerun `pip install -r requirements.txt`.

- [ ] **Step 5: Commit**

```bash
git add app/integrations/google_analytics.py app/tests/test_google_analytics_integration.py
git commit -m "feat(integrations): add Google Analytics Data API client with impersonation"
```

---

## Task 5: GA Pydantic schemas

**Files:**
- Create: `app/schemas/google_analytics.py`
- Test: `app/tests/test_google_analytics_schemas.py`

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_google_analytics_schemas.py`:

```python
from app.schemas.google_analytics import (
    EventRow,
    GeoRow,
    PlatformRow,
    PlatformsBreakdown,
    PropertyInfo,
    PropertyOverviewResponse,
    TopPageRow,
    TrafficTimeSeries,
)


def test_property_info_round_trip():
    p = PropertyInfo(id="506611499", name="Sunflower")
    assert p.model_dump() == {"id": "506611499", "name": "Sunflower"}


def test_property_overview_accepts_empty_reports():
    resp = PropertyOverviewResponse(
        property_id="506611499",
        property_name="Sunflower",
        time_range="7d",
        cached_until="2026-04-19T15:00:00Z",
        traffic=TrafficTimeSeries(
            labels=[], active_users=[], new_users=[], sessions=[],
            engaged_sessions=[], engagement_rate=[],
            avg_session_duration=[], bounce_rate=[],
        ),
        top_pages=[],
        platforms=PlatformsBreakdown(device=[], os=[], browser=[]),
        geography=[],
        events=[],
        partial=False,
        failed_reports=[],
    )
    d = resp.model_dump()
    assert d["property_id"] == "506611499"
    assert d["partial"] is False


def test_partial_failure_lists_failed_reports():
    resp = PropertyOverviewResponse(
        property_id="506611499",
        property_name="Sunflower",
        time_range="7d",
        cached_until="2026-04-19T15:00:00Z",
        traffic=TrafficTimeSeries(
            labels=[], active_users=[], new_users=[], sessions=[],
            engaged_sessions=[], engagement_rate=[],
            avg_session_duration=[], bounce_rate=[],
        ),
        top_pages=[TopPageRow(path="/", title="Home", views=10, users=5, avg_duration=0.0)],
        platforms=PlatformsBreakdown(
            device=[PlatformRow(label="desktop", users=5, sessions=5)],
            os=[], browser=[],
        ),
        geography=[GeoRow(country="Uganda", city="Kampala", users=5, sessions=5)],
        events=[EventRow(name="page_view", count=10, users=5)],
        partial=True,
        failed_reports=["events"],
    )
    assert resp.partial is True
    assert resp.failed_reports == ["events"]
```

- [ ] **Step 2: Run to verify failure**

```
pytest app/tests/test_google_analytics_schemas.py -v
```
Expected: FAIL (module missing).

- [ ] **Step 3: Create `app/schemas/google_analytics.py`**

```python
"""Pydantic response schemas for the Google Analytics admin endpoints."""

from pydantic import BaseModel, Field


class PropertyInfo(BaseModel):
    id: str
    name: str


class TrafficTimeSeries(BaseModel):
    """All lists are aligned to `labels` (one entry per date)."""

    labels: list[str]
    active_users: list[int]
    new_users: list[int]
    sessions: list[int]
    engaged_sessions: list[int]
    engagement_rate: list[float]
    avg_session_duration: list[float]
    bounce_rate: list[float]


class TopPageRow(BaseModel):
    path: str
    title: str
    views: int
    users: int
    avg_duration: float


class PlatformRow(BaseModel):
    label: str
    users: int
    sessions: int


class PlatformsBreakdown(BaseModel):
    device: list[PlatformRow]
    os: list[PlatformRow]
    browser: list[PlatformRow]


class GeoRow(BaseModel):
    country: str
    city: str
    users: int
    sessions: int


class EventRow(BaseModel):
    name: str
    count: int
    users: int


class PropertyOverviewResponse(BaseModel):
    property_id: str
    property_name: str
    time_range: str
    cached_until: str = Field(
        description="ISO-8601 timestamp when the oldest cached report expires."
    )
    traffic: TrafficTimeSeries
    top_pages: list[TopPageRow]
    platforms: PlatformsBreakdown
    geography: list[GeoRow]
    events: list[EventRow]
    partial: bool = False
    failed_reports: list[str] = Field(default_factory=list)


class PropertiesListResponse(BaseModel):
    properties: list[PropertyInfo]
```

- [ ] **Step 4: Run tests**

```
pytest app/tests/test_google_analytics_schemas.py -v
```
Expected: all 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/schemas/google_analytics.py app/tests/test_google_analytics_schemas.py
git commit -m "feat(schemas): add Pydantic models for Google Analytics responses"
```

---

## Task 6: GA service helpers — time range + allowlist

**Files:**
- Create: `app/services/google_analytics_service.py` (partial — helpers only)
- Test: `app/tests/test_google_analytics_service.py`

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_google_analytics_service.py`:

```python
import pytest

from app.core.exceptions import BadRequestError
from app.services.google_analytics_service import (
    REPORT_NAMES,
    GoogleAnalyticsService,
    _parse_time_range,
)


class TestParseTimeRange:
    @pytest.mark.parametrize(
        "tr,expected",
        [
            ("24h", ("yesterday", "today")),
            ("7d", ("7daysAgo", "today")),
            ("30d", ("30daysAgo", "today")),
            ("60d", ("60daysAgo", "today")),
            ("90d", ("90daysAgo", "today")),
        ],
    )
    def test_supported_values(self, tr, expected):
        assert _parse_time_range(tr) == expected

    def test_invalid_value_raises(self):
        with pytest.raises(BadRequestError, match="Invalid time_range"):
            _parse_time_range("1y")


class TestPropertyAllowlist:
    def test_validate_accepts_known_property(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.settings.ga_properties_raw",
            "506611499:Sunflower,448469065:Sunbird Speech",
        )
        svc = GoogleAnalyticsService(
            ga_client=None, cache=None  # type: ignore[arg-type]
        )
        # Should not raise
        svc._require_allowed_property("506611499")

    def test_validate_rejects_unknown_property(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.settings.ga_properties_raw",
            "506611499:Sunflower",
        )
        svc = GoogleAnalyticsService(
            ga_client=None, cache=None  # type: ignore[arg-type]
        )
        with pytest.raises(BadRequestError, match="not in allowlist"):
            svc._require_allowed_property("999999999")


def test_report_names_matches_aggregator_keys():
    assert set(REPORT_NAMES) == {
        "traffic", "pages", "platforms", "geography", "events"
    }
```

- [ ] **Step 2: Run to verify failure**

```
pytest app/tests/test_google_analytics_service.py -v
```
Expected: FAIL (module missing).

- [ ] **Step 3: Create `app/services/google_analytics_service.py` (initial, helpers only)**

```python
"""Google Analytics orchestration service.

Responsibilities:
- Map admin-facing time ranges to GA date range values
- Run and cache individual reports (traffic, pages, platforms, geo, events)
- Aggregate reports, shape results for the frontend, tolerate partial failures
"""

from __future__ import annotations

from typing import Tuple

from app.core.config import settings
from app.core.exceptions import BadRequestError
from app.integrations.google_analytics import GoogleAnalyticsClient
from app.services.cache import CacheBackend

REPORT_NAMES: Tuple[str, ...] = (
    "traffic", "pages", "platforms", "geography", "events"
)

_TIME_RANGE_MAP: dict[str, tuple[str, str]] = {
    "24h": ("yesterday", "today"),
    "7d": ("7daysAgo", "today"),
    "30d": ("30daysAgo", "today"),
    "60d": ("60daysAgo", "today"),
    "90d": ("90daysAgo", "today"),
}


def _parse_time_range(time_range: str) -> tuple[str, str]:
    try:
        return _TIME_RANGE_MAP[time_range]
    except KeyError as exc:
        raise BadRequestError(
            f"Invalid time_range '{time_range}'. "
            f"Supported: {sorted(_TIME_RANGE_MAP.keys())}"
        ) from exc


class GoogleAnalyticsService:
    def __init__(
        self, ga_client: GoogleAnalyticsClient, cache: CacheBackend
    ) -> None:
        self._ga = ga_client
        self._cache = cache

    def _require_allowed_property(self, property_id: str) -> str:
        allowlist = settings.ga_properties
        if property_id not in allowlist:
            raise BadRequestError(
                f"Property '{property_id}' is not in allowlist."
            )
        return allowlist[property_id]
```

- [ ] **Step 4: Run tests**

```
pytest app/tests/test_google_analytics_service.py -v
```
Expected: all 4 tests in the 3 test classes PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/google_analytics_service.py app/tests/test_google_analytics_service.py
git commit -m "feat(ga): add service skeleton with time-range parsing and property allowlist"
```

---

## Task 7: GA service — individual report methods

**Files:**
- Modify: `app/services/google_analytics_service.py`
- Modify: `app/tests/test_google_analytics_service.py`
- Create: `app/tests/fixtures/ga/__init__.py` (empty)
- Create: `app/tests/fixtures/ga/responses.py`

- [ ] **Step 1: Create fixtures for GA-response shapes**

Create `app/tests/fixtures/ga/__init__.py` as an empty file, then create `app/tests/fixtures/ga/responses.py`:

```python
"""Canned GoogleAnalyticsClient.run_report outputs for service tests."""

TRAFFIC_RESPONSE = {
    "dimension_headers": ["date"],
    "metric_headers": [
        "activeUsers", "newUsers", "sessions", "engagedSessions",
        "engagementRate", "averageSessionDuration", "bounceRate",
    ],
    "rows": [
        {"dimensions": ["20260413"], "metrics": ["100", "30", "120", "80", "0.67", "95.5", "0.33"]},
        {"dimensions": ["20260414"], "metrics": ["110", "35", "130", "85", "0.65", "102.1", "0.35"]},
    ],
}

TOP_PAGES_RESPONSE = {
    "dimension_headers": ["pagePath", "pageTitle"],
    "metric_headers": ["screenPageViews", "activeUsers", "averageSessionDuration"],
    "rows": [
        {"dimensions": ["/dashboard", "Dashboard"], "metrics": ["200", "150", "120.5"]},
        {"dimensions": ["/login", "Login"], "metrics": ["180", "170", "45.2"]},
    ],
}

PLATFORM_RESPONSE = {
    "dimension_headers": ["deviceCategory", "operatingSystem", "browser"],
    "metric_headers": ["activeUsers", "sessions"],
    "rows": [
        {"dimensions": ["desktop", "Windows", "Chrome"], "metrics": ["500", "600"]},
        {"dimensions": ["mobile", "Android", "Chrome"], "metrics": ["300", "350"]},
        {"dimensions": ["mobile", "iOS", "Safari"], "metrics": ["100", "120"]},
    ],
}

GEO_RESPONSE = {
    "dimension_headers": ["country", "city"],
    "metric_headers": ["activeUsers", "sessions"],
    "rows": [
        {"dimensions": ["Uganda", "Kampala"], "metrics": ["800", "900"]},
        {"dimensions": ["Kenya", "Nairobi"], "metrics": ["100", "120"]},
    ],
}

EVENTS_RESPONSE = {
    "dimension_headers": ["eventName"],
    "metric_headers": ["eventCount", "totalUsers"],
    "rows": [
        {"dimensions": ["page_view"], "metrics": ["1200", "400"]},
        {"dimensions": ["session_start"], "metrics": ["450", "400"]},
    ],
}
```

- [ ] **Step 2: Add failing tests for each report method**

Append to `app/tests/test_google_analytics_service.py`:

```python
from unittest.mock import AsyncMock

from app.services.google_analytics_service import GoogleAnalyticsService
from app.tests.fixtures.ga.responses import (
    EVENTS_RESPONSE,
    GEO_RESPONSE,
    PLATFORM_RESPONSE,
    TOP_PAGES_RESPONSE,
    TRAFFIC_RESPONSE,
)


def _service_with_mocks(monkeypatch, response):
    monkeypatch.setattr(
        "app.core.config.settings.ga_properties_raw",
        "506611499:Sunflower,448469065:Sunbird Speech",
    )
    ga = AsyncMock()
    ga.run_report.return_value = response

    async def miss(_key):
        return None

    cache = AsyncMock()
    cache.get = AsyncMock(side_effect=miss)
    cache.set = AsyncMock()

    return GoogleAnalyticsService(ga_client=ga, cache=cache), ga, cache


class TestTrafficReport:
    async def test_returns_aligned_series(self, monkeypatch):
        svc, ga, cache = _service_with_mocks(monkeypatch, TRAFFIC_RESPONSE)
        out = await svc.get_traffic_overview("506611499", "7d")
        assert out["labels"] == ["20260413", "20260414"]
        assert out["active_users"] == [100, 110]
        assert out["new_users"] == [30, 35]
        assert out["engagement_rate"] == pytest.approx([0.67, 0.65])
        ga.run_report.assert_awaited_once()
        cache.set.assert_awaited_once()

    async def test_uses_cache_on_hit(self, monkeypatch):
        svc, ga, cache = _service_with_mocks(monkeypatch, TRAFFIC_RESPONSE)
        cached = {
            "cached_at": "2026-04-19T14:00:00Z",
            "data": {"labels": ["cached"], "active_users": [1],
                     "new_users": [0], "sessions": [1], "engaged_sessions": [1],
                     "engagement_rate": [1.0], "avg_session_duration": [0.0],
                     "bounce_rate": [0.0]},
        }
        cache.get = AsyncMock(return_value=cached)
        out = await svc.get_traffic_overview("506611499", "7d")
        assert out["labels"] == ["cached"]
        ga.run_report.assert_not_awaited()


class TestTopPages:
    async def test_shapes_rows(self, monkeypatch):
        svc, ga, _ = _service_with_mocks(monkeypatch, TOP_PAGES_RESPONSE)
        out = await svc.get_top_pages("506611499", "7d", limit=10)
        assert out == [
            {"path": "/dashboard", "title": "Dashboard", "views": 200,
             "users": 150, "avg_duration": 120.5},
            {"path": "/login", "title": "Login", "views": 180,
             "users": 170, "avg_duration": 45.2},
        ]


class TestPlatformBreakdown:
    async def test_groups_by_dimension(self, monkeypatch):
        svc, _, _ = _service_with_mocks(monkeypatch, PLATFORM_RESPONSE)
        out = await svc.get_platform_breakdown("506611499", "7d")
        # Device is sum across rows
        device_map = {r["label"]: r["users"] for r in out["device"]}
        assert device_map == {"desktop": 500, "mobile": 400}
        # OS rollup
        os_map = {r["label"]: r["users"] for r in out["os"]}
        assert os_map == {"Windows": 500, "Android": 300, "iOS": 100}
        # Browser rollup
        browser_map = {r["label"]: r["users"] for r in out["browser"]}
        assert browser_map == {"Chrome": 800, "Safari": 100}


class TestGeoBreakdown:
    async def test_returns_country_city_rows(self, monkeypatch):
        svc, _, _ = _service_with_mocks(monkeypatch, GEO_RESPONSE)
        out = await svc.get_geo_breakdown("506611499", "7d", limit=20)
        assert out == [
            {"country": "Uganda", "city": "Kampala", "users": 800, "sessions": 900},
            {"country": "Kenya", "city": "Nairobi", "users": 100, "sessions": 120},
        ]


class TestTopEvents:
    async def test_shapes_rows(self, monkeypatch):
        svc, _, _ = _service_with_mocks(monkeypatch, EVENTS_RESPONSE)
        out = await svc.get_top_events("506611499", "7d", limit=15)
        assert out == [
            {"name": "page_view", "count": 1200, "users": 400},
            {"name": "session_start", "count": 450, "users": 400},
        ]
```

- [ ] **Step 3: Run to verify failure**

```
pytest app/tests/test_google_analytics_service.py -v
```
Expected: FAIL (methods do not yet exist).

- [ ] **Step 4: Extend `app/services/google_analytics_service.py`**

Append to the `GoogleAnalyticsService` class:

```python
    async def _cached_or_fetch(
        self, cache_key: str, fetch_fn
    ) -> dict:
        """Return cached payload; on miss, fetch and cache with configured TTL."""
        from datetime import datetime, timezone

        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached["data"]

        data = await fetch_fn()
        wrapped = {
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        await self._cache.set(
            cache_key, wrapped, ttl_seconds=settings.ga_cache_ttl_seconds
        )
        return data

    async def get_traffic_overview(
        self, property_id: str, time_range: str
    ) -> dict:
        self._require_allowed_property(property_id)
        key = f"ga:{property_id}:traffic:{time_range}"
        start, end = _parse_time_range(time_range)

        async def fetch():
            resp = await self._ga.run_report(
                property_id=property_id,
                dimensions=["date"],
                metrics=[
                    "activeUsers", "newUsers", "sessions", "engagedSessions",
                    "engagementRate", "averageSessionDuration", "bounceRate",
                ],
                start_date=start,
                end_date=end,
            )
            labels = [r["dimensions"][0] for r in resp["rows"]]
            cols = list(zip(*[r["metrics"] for r in resp["rows"]])) if resp["rows"] else [()] * 7
            to_int = lambda xs: [int(x) for x in xs]
            to_float = lambda xs: [float(x) for x in xs]
            return {
                "labels": labels,
                "active_users": to_int(cols[0]),
                "new_users": to_int(cols[1]),
                "sessions": to_int(cols[2]),
                "engaged_sessions": to_int(cols[3]),
                "engagement_rate": to_float(cols[4]),
                "avg_session_duration": to_float(cols[5]),
                "bounce_rate": to_float(cols[6]),
            }

        return await self._cached_or_fetch(key, fetch)

    async def get_top_pages(
        self, property_id: str, time_range: str, limit: int = 10
    ) -> list[dict]:
        self._require_allowed_property(property_id)
        key = f"ga:{property_id}:pages:{time_range}"
        start, end = _parse_time_range(time_range)

        async def fetch():
            from google.analytics.data_v1beta.types import OrderBy

            resp = await self._ga.run_report(
                property_id=property_id,
                dimensions=["pagePath", "pageTitle"],
                metrics=["screenPageViews", "activeUsers", "averageSessionDuration"],
                start_date=start,
                end_date=end,
                limit=limit,
                order_bys=[
                    OrderBy(
                        metric=OrderBy.MetricOrderBy(metric_name="screenPageViews"),
                        desc=True,
                    )
                ],
            )
            return [
                {
                    "path": r["dimensions"][0],
                    "title": r["dimensions"][1],
                    "views": int(r["metrics"][0]),
                    "users": int(r["metrics"][1]),
                    "avg_duration": float(r["metrics"][2]),
                }
                for r in resp["rows"]
            ]

        return await self._cached_or_fetch(key, fetch)

    async def get_platform_breakdown(
        self, property_id: str, time_range: str
    ) -> dict:
        self._require_allowed_property(property_id)
        key = f"ga:{property_id}:platforms:{time_range}"
        start, end = _parse_time_range(time_range)

        async def fetch():
            resp = await self._ga.run_report(
                property_id=property_id,
                dimensions=["deviceCategory", "operatingSystem", "browser"],
                metrics=["activeUsers", "sessions"],
                start_date=start,
                end_date=end,
            )
            device: dict[str, dict] = {}
            os_: dict[str, dict] = {}
            browser: dict[str, dict] = {}
            for row in resp["rows"]:
                dev, osn, br = row["dimensions"]
                users = int(row["metrics"][0])
                sessions = int(row["metrics"][1])
                for bucket, label in ((device, dev), (os_, osn), (browser, br)):
                    entry = bucket.setdefault(
                        label, {"label": label, "users": 0, "sessions": 0}
                    )
                    entry["users"] += users
                    entry["sessions"] += sessions
            sort_desc = lambda d: sorted(d.values(), key=lambda x: -x["users"])
            return {
                "device": sort_desc(device),
                "os": sort_desc(os_),
                "browser": sort_desc(browser),
            }

        return await self._cached_or_fetch(key, fetch)

    async def get_geo_breakdown(
        self, property_id: str, time_range: str, limit: int = 20
    ) -> list[dict]:
        self._require_allowed_property(property_id)
        key = f"ga:{property_id}:geography:{time_range}"
        start, end = _parse_time_range(time_range)

        async def fetch():
            from google.analytics.data_v1beta.types import OrderBy

            resp = await self._ga.run_report(
                property_id=property_id,
                dimensions=["country", "city"],
                metrics=["activeUsers", "sessions"],
                start_date=start,
                end_date=end,
                limit=limit,
                order_bys=[
                    OrderBy(
                        metric=OrderBy.MetricOrderBy(metric_name="activeUsers"),
                        desc=True,
                    )
                ],
            )
            return [
                {
                    "country": r["dimensions"][0],
                    "city": r["dimensions"][1],
                    "users": int(r["metrics"][0]),
                    "sessions": int(r["metrics"][1]),
                }
                for r in resp["rows"]
            ]

        return await self._cached_or_fetch(key, fetch)

    async def get_top_events(
        self, property_id: str, time_range: str, limit: int = 15
    ) -> list[dict]:
        self._require_allowed_property(property_id)
        key = f"ga:{property_id}:events:{time_range}"
        start, end = _parse_time_range(time_range)

        async def fetch():
            from google.analytics.data_v1beta.types import OrderBy

            resp = await self._ga.run_report(
                property_id=property_id,
                dimensions=["eventName"],
                metrics=["eventCount", "totalUsers"],
                start_date=start,
                end_date=end,
                limit=limit,
                order_bys=[
                    OrderBy(
                        metric=OrderBy.MetricOrderBy(metric_name="eventCount"),
                        desc=True,
                    )
                ],
            )
            return [
                {
                    "name": r["dimensions"][0],
                    "count": int(r["metrics"][0]),
                    "users": int(r["metrics"][1]),
                }
                for r in resp["rows"]
            ]

        return await self._cached_or_fetch(key, fetch)
```

- [ ] **Step 5: Run tests**

```
pytest app/tests/test_google_analytics_service.py -v
```
Expected: all report tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/google_analytics_service.py app/tests/test_google_analytics_service.py app/tests/fixtures
git commit -m "feat(ga): add per-report methods with caching and response shaping"
```

---

## Task 8: GA service aggregator with partial-failure handling

**Files:**
- Modify: `app/services/google_analytics_service.py`
- Modify: `app/tests/test_google_analytics_service.py`

- [ ] **Step 1: Write the failing test**

Append to `app/tests/test_google_analytics_service.py`:

```python
class TestAggregator:
    async def test_overview_returns_all_reports(self, monkeypatch):
        from app.tests.fixtures.ga.responses import (
            EVENTS_RESPONSE, GEO_RESPONSE, PLATFORM_RESPONSE,
            TOP_PAGES_RESPONSE, TRAFFIC_RESPONSE,
        )
        monkeypatch.setattr(
            "app.core.config.settings.ga_properties_raw",
            "506611499:Sunflower",
        )
        ga = AsyncMock()
        responses = [
            TRAFFIC_RESPONSE, TOP_PAGES_RESPONSE, PLATFORM_RESPONSE,
            GEO_RESPONSE, EVENTS_RESPONSE,
        ]
        ga.run_report = AsyncMock(side_effect=responses)

        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)
        cache.set = AsyncMock()

        svc = GoogleAnalyticsService(ga_client=ga, cache=cache)
        out = await svc.get_property_overview("506611499", "7d")

        assert out["property_id"] == "506611499"
        assert out["property_name"] == "Sunflower"
        assert out["time_range"] == "7d"
        assert out["partial"] is False
        assert out["failed_reports"] == []
        assert out["traffic"]["labels"] == ["20260413", "20260414"]
        assert len(out["top_pages"]) == 2

    async def test_overview_tolerates_partial_failure(self, monkeypatch):
        from app.tests.fixtures.ga.responses import (
            EVENTS_RESPONSE, GEO_RESPONSE, PLATFORM_RESPONSE,
            TOP_PAGES_RESPONSE, TRAFFIC_RESPONSE,
        )
        monkeypatch.setattr(
            "app.core.config.settings.ga_properties_raw",
            "506611499:Sunflower",
        )
        ga = AsyncMock()
        # Make the events call raise
        ga.run_report = AsyncMock(side_effect=[
            TRAFFIC_RESPONSE, TOP_PAGES_RESPONSE, PLATFORM_RESPONSE,
            GEO_RESPONSE, RuntimeError("quota"),
        ])

        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)
        cache.set = AsyncMock()

        svc = GoogleAnalyticsService(ga_client=ga, cache=cache)
        out = await svc.get_property_overview("506611499", "7d")

        assert out["partial"] is True
        assert out["failed_reports"] == ["events"]
        assert out["events"] == []          # empty default on failure
        assert out["traffic"]["labels"] == ["20260413", "20260414"]  # succeeded

    async def test_force_refresh_deletes_cache_then_refetches(self, monkeypatch):
        from app.tests.fixtures.ga.responses import (
            EVENTS_RESPONSE, GEO_RESPONSE, PLATFORM_RESPONSE,
            TOP_PAGES_RESPONSE, TRAFFIC_RESPONSE,
        )
        monkeypatch.setattr(
            "app.core.config.settings.ga_properties_raw",
            "506611499:Sunflower",
        )
        ga = AsyncMock()
        ga.run_report = AsyncMock(side_effect=[
            TRAFFIC_RESPONSE, TOP_PAGES_RESPONSE, PLATFORM_RESPONSE,
            GEO_RESPONSE, EVENTS_RESPONSE,
        ])

        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)  # miss after delete
        cache.set = AsyncMock()
        cache.delete = AsyncMock()

        svc = GoogleAnalyticsService(ga_client=ga, cache=cache)
        await svc.get_property_overview("506611499", "7d", force_refresh=True)

        # delete called once per report (5 total)
        deleted_keys = {c.args[0] for c in cache.delete.await_args_list}
        assert deleted_keys == {
            "ga:506611499:traffic:7d",
            "ga:506611499:pages:7d",
            "ga:506611499:platforms:7d",
            "ga:506611499:geography:7d",
            "ga:506611499:events:7d",
        }
```

- [ ] **Step 2: Run to verify failure**

```
pytest app/tests/test_google_analytics_service.py::TestAggregator -v
```
Expected: FAIL (`get_property_overview` not defined).

- [ ] **Step 3: Extend the service**

Append to `GoogleAnalyticsService`:

```python
    async def get_property_overview(
        self,
        property_id: str,
        time_range: str,
        force_refresh: bool = False,
    ) -> dict:
        """Run all 5 reports concurrently; tolerate individual failures."""
        import asyncio
        import logging
        from datetime import datetime, timedelta, timezone

        logger = logging.getLogger(__name__)
        property_name = self._require_allowed_property(property_id)
        _parse_time_range(time_range)  # validate early

        if force_refresh:
            for report in REPORT_NAMES:
                await self._cache.delete(f"ga:{property_id}:{report}:{time_range}")

        traffic_task = self.get_traffic_overview(property_id, time_range)
        pages_task = self.get_top_pages(property_id, time_range)
        platforms_task = self.get_platform_breakdown(property_id, time_range)
        geo_task = self.get_geo_breakdown(property_id, time_range)
        events_task = self.get_top_events(property_id, time_range)

        results = await asyncio.gather(
            traffic_task, pages_task, platforms_task, geo_task, events_task,
            return_exceptions=True,
        )
        labels = ("traffic", "pages", "platforms", "geography", "events")
        payload: dict = {}
        failed: list[str] = []
        for label, result in zip(labels, results):
            if isinstance(result, Exception):
                logger.warning(
                    "GA report '%s' failed for property %s/%s: %s",
                    label, property_id, time_range, result,
                )
                failed.append(label)
                payload[label] = _empty_payload_for(label)
            else:
                payload[label] = result

        cached_until = (
            datetime.now(timezone.utc)
            + timedelta(seconds=settings.ga_cache_ttl_seconds)
        ).isoformat()

        return {
            "property_id": property_id,
            "property_name": property_name,
            "time_range": time_range,
            "cached_until": cached_until,
            "traffic": payload["traffic"],
            "top_pages": payload["pages"],
            "platforms": payload["platforms"],
            "geography": payload["geography"],
            "events": payload["events"],
            "partial": bool(failed),
            "failed_reports": failed,
        }


def _empty_payload_for(label: str):
    """Default shape when an individual report fails."""
    if label == "traffic":
        return {
            "labels": [], "active_users": [], "new_users": [], "sessions": [],
            "engaged_sessions": [], "engagement_rate": [],
            "avg_session_duration": [], "bounce_rate": [],
        }
    if label == "platforms":
        return {"device": [], "os": [], "browser": []}
    return []  # pages, geography, events
```

- [ ] **Step 4: Run tests**

```
pytest app/tests/test_google_analytics_service.py -v
```
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/google_analytics_service.py app/tests/test_google_analytics_service.py
git commit -m "feat(ga): aggregator with concurrent fetch and partial-failure handling"
```

---

## Task 9: Service DI wiring

**Files:**
- Modify: `app/services/google_analytics_service.py`
- Modify: `app/deps.py`

- [ ] **Step 1: Add singleton factory at the bottom of `app/services/google_analytics_service.py`**

```python
_instance: GoogleAnalyticsService | None = None


def get_google_analytics_service() -> GoogleAnalyticsService:
    global _instance
    if _instance is None:
        from app.integrations.google_analytics import get_google_analytics_client
        from app.services.cache import get_cache_backend

        _instance = GoogleAnalyticsService(
            ga_client=get_google_analytics_client(),
            cache=get_cache_backend(),
        )
    return _instance
```

- [ ] **Step 2: Wire DI alias in `app/deps.py`**

Under the service imports, add:

```python
from app.services.google_analytics_service import (
    GoogleAnalyticsService,
    get_google_analytics_service,
)
```

Under the Annotated aliases:

```python
GoogleAnalyticsServiceDep = Annotated[
    GoogleAnalyticsService, Depends(get_google_analytics_service)
]
```

Add to `__all__`: `"GoogleAnalyticsServiceDep"`, `"GoogleAnalyticsService"`.

- [ ] **Step 3: Run all backend tests — smoke**

```
pytest app/tests/ -v -k "config or cache or google_analytics"
```
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add app/services/google_analytics_service.py app/deps.py
git commit -m "feat(deps): register GoogleAnalyticsService factory and DI alias"
```

---

## Task 10: Router + `/properties` endpoint + mount in api.py

**Files:**
- Create: `app/routers/google_analytics.py`
- Modify: `app/api.py`
- Test: `app/tests/test_google_analytics_router.py`

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_google_analytics_router.py`:

```python
from unittest.mock import AsyncMock, patch

import pytest


async def test_properties_requires_auth(async_client):
    resp = await async_client.get("/api/admin/google-analytics/properties")
    assert resp.status_code == 401


async def test_properties_requires_admin(authenticated_client):
    resp = await authenticated_client.get("/api/admin/google-analytics/properties")
    assert resp.status_code in (401, 403)


async def test_properties_returns_list_when_enabled(admin_client, monkeypatch):
    monkeypatch.setattr(
        "app.core.config.settings.ga_properties_raw",
        "506611499:Sunflower,448469065:Sunbird Speech",
    )
    monkeypatch.setattr(
        "app.core.config.settings.ga_impersonation_target",
        "ga-reader@test.iam.gserviceaccount.com",
    )
    resp = await admin_client.get("/api/admin/google-analytics/properties")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {
        "properties": [
            {"id": "506611499", "name": "Sunflower"},
            {"id": "448469065", "name": "Sunbird Speech"},
        ]
    }


async def test_properties_returns_503_when_disabled(admin_client, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.ga_properties_raw", "")
    monkeypatch.setattr(
        "app.core.config.settings.ga_impersonation_target", None
    )
    resp = await admin_client.get("/api/admin/google-analytics/properties")
    assert resp.status_code == 503
```

> If your `conftest.py` doesn't yet have an `admin_client` fixture, add one. Check first:
> `grep -n "admin_client\|admin_user" app/tests/conftest.py`.
> If absent, add:
> ```python
> @pytest.fixture
> async def admin_client(async_client, admin_user):
>     async_client.headers.update({"Authorization": f"Bearer {admin_user['token']}"})
>     return async_client
> ```
> Then commit the fixture addition in this same task.

- [ ] **Step 2: Run to verify failure**

```
pytest app/tests/test_google_analytics_router.py -v
```
Expected: FAIL (no route mounted).

- [ ] **Step 3: Create `app/routers/google_analytics.py`**

```python
"""Admin routes for surfacing Google Analytics data."""

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.deps import CurrentAdminDep, GoogleAnalyticsServiceDep
from app.schemas.google_analytics import (
    PropertiesListResponse,
    PropertyInfo,
    PropertyOverviewResponse,
)

router = APIRouter()


def _require_enabled():
    if not settings.ga_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Analytics is not configured.",
        )


@router.get("/properties", response_model=PropertiesListResponse)
async def list_properties(_: CurrentAdminDep):
    _require_enabled()
    return PropertiesListResponse(
        properties=[
            PropertyInfo(id=pid, name=name)
            for pid, name in settings.ga_properties.items()
        ]
    )
```

- [ ] **Step 4: Mount the router in `app/api.py`**

Add the import next to the other router imports (~line 31):

```python
from app.routers.google_analytics import router as google_analytics_router
```

Add the include below `admin_analytics_router` (~line 222):

```python
app.include_router(
    google_analytics_router,
    prefix="/api/admin/google-analytics",
    tags=["Admin Google Analytics"],
)
```

- [ ] **Step 5: Run tests**

```
pytest app/tests/test_google_analytics_router.py -v
```
Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/routers/google_analytics.py app/api.py app/tests/test_google_analytics_router.py app/tests/conftest.py
git commit -m "feat(ga-router): add /properties endpoint and mount under /api/admin/google-analytics"
```

---

## Task 11: `/overview` endpoint (TDD)

**Files:**
- Modify: `app/routers/google_analytics.py`
- Modify: `app/tests/test_google_analytics_router.py`

- [ ] **Step 1: Write the failing test**

Append to `app/tests/test_google_analytics_router.py`:

```python
from app.tests.fixtures.ga.responses import (
    EVENTS_RESPONSE, GEO_RESPONSE, PLATFORM_RESPONSE,
    TOP_PAGES_RESPONSE, TRAFFIC_RESPONSE,
)


@pytest.fixture
def enable_ga(monkeypatch):
    monkeypatch.setattr(
        "app.core.config.settings.ga_properties_raw",
        "506611499:Sunflower,448469065:Sunbird Speech",
    )
    monkeypatch.setattr(
        "app.core.config.settings.ga_impersonation_target",
        "ga-reader@test.iam.gserviceaccount.com",
    )


async def test_overview_returns_all_reports(admin_client, enable_ga):
    # BetaAnalyticsDataClient.run_report is sync (we wrap it with
    # asyncio.to_thread in the integration layer), so use MagicMock,
    # not AsyncMock, for the underlying client.
    from unittest.mock import MagicMock

    with patch("app.integrations.google_analytics.google.auth.default",
               return_value=(MagicMock(), None)), \
         patch("app.integrations.google_analytics.impersonated_credentials.Credentials"), \
         patch("app.integrations.google_analytics.BetaAnalyticsDataClient") as mock_cls:
        # Reset singleton between tests
        import app.services.google_analytics_service as svc_mod
        import app.integrations.google_analytics as int_mod
        svc_mod._instance = None
        int_mod._instance = None

        ga_client = MagicMock()
        ga_client.run_report = MagicMock(side_effect=[
            _to_proto(TRAFFIC_RESPONSE),
            _to_proto(TOP_PAGES_RESPONSE),
            _to_proto(PLATFORM_RESPONSE),
            _to_proto(GEO_RESPONSE),
            _to_proto(EVENTS_RESPONSE),
        ])
        mock_cls.return_value = ga_client

        resp = await admin_client.get(
            "/api/admin/google-analytics/overview",
            params={"property_id": "506611499", "time_range": "7d"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["property_id"] == "506611499"
    assert data["property_name"] == "Sunflower"
    assert data["partial"] is False
    assert data["traffic"]["labels"] == ["20260413", "20260414"]


async def test_overview_rejects_unknown_property(admin_client, enable_ga):
    resp = await admin_client.get(
        "/api/admin/google-analytics/overview",
        params={"property_id": "9999", "time_range": "7d"},
    )
    assert resp.status_code == 400


async def test_overview_rejects_invalid_time_range(admin_client, enable_ga):
    resp = await admin_client.get(
        "/api/admin/google-analytics/overview",
        params={"property_id": "506611499", "time_range": "1y"},
    )
    assert resp.status_code == 400


def _to_proto(response_dict: dict):
    """Convert a fixture dict back into a mock that quacks like a RunReportResponse."""
    from unittest.mock import MagicMock

    proto = MagicMock()
    proto.dimension_headers = [MagicMock(name=n) for n in response_dict["dimension_headers"]]
    for hdr, name in zip(proto.dimension_headers, response_dict["dimension_headers"]):
        hdr.name = name
    proto.metric_headers = [MagicMock(name=n) for n in response_dict["metric_headers"]]
    for hdr, name in zip(proto.metric_headers, response_dict["metric_headers"]):
        hdr.name = name
    rows = []
    for row_data in response_dict["rows"]:
        row = MagicMock()
        row.dimension_values = [MagicMock(value=v) for v in row_data["dimensions"]]
        for d, v in zip(row.dimension_values, row_data["dimensions"]):
            d.value = v
        row.metric_values = [MagicMock(value=v) for v in row_data["metrics"]]
        for m, v in zip(row.metric_values, row_data["metrics"]):
            m.value = v
        rows.append(row)
    proto.rows = rows
    return proto
```

- [ ] **Step 2: Run to verify failure**

```
pytest app/tests/test_google_analytics_router.py::test_overview_returns_all_reports -v
```
Expected: FAIL (route 404).

- [ ] **Step 3: Add the route to `app/routers/google_analytics.py`**

Append:

```python
@router.get("/overview", response_model=PropertyOverviewResponse)
async def get_overview(
    property_id: str,
    ga_service: GoogleAnalyticsServiceDep,
    _: CurrentAdminDep,
    time_range: str = "7d",
):
    _require_enabled()
    data = await ga_service.get_property_overview(property_id, time_range)
    return PropertyOverviewResponse(**data)
```

- [ ] **Step 4: Run tests**

```
pytest app/tests/test_google_analytics_router.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/routers/google_analytics.py app/tests/test_google_analytics_router.py
git commit -m "feat(ga-router): add /overview endpoint with admin guard"
```

---

## Task 12: `/refresh` endpoint (TDD)

**Files:**
- Modify: `app/routers/google_analytics.py`
- Modify: `app/tests/test_google_analytics_router.py`

- [ ] **Step 1: Write the failing test**

Append to `app/tests/test_google_analytics_router.py`:

```python
async def test_refresh_busts_cache_then_returns_fresh(admin_client, enable_ga):
    from unittest.mock import MagicMock

    with patch("app.integrations.google_analytics.google.auth.default",
               return_value=(MagicMock(), None)), \
         patch("app.integrations.google_analytics.impersonated_credentials.Credentials"), \
         patch("app.integrations.google_analytics.BetaAnalyticsDataClient") as mock_cls:
        import app.services.google_analytics_service as svc_mod
        import app.integrations.google_analytics as int_mod
        svc_mod._instance = None
        int_mod._instance = None

        ga_client = MagicMock()
        ga_client.run_report = MagicMock(side_effect=[
            _to_proto(TRAFFIC_RESPONSE),
            _to_proto(TOP_PAGES_RESPONSE),
            _to_proto(PLATFORM_RESPONSE),
            _to_proto(GEO_RESPONSE),
            _to_proto(EVENTS_RESPONSE),
        ])
        mock_cls.return_value = ga_client

        resp = await admin_client.post(
            "/api/admin/google-analytics/refresh",
            params={"property_id": "506611499", "time_range": "7d"},
        )

    assert resp.status_code == 200
    assert resp.json()["property_id"] == "506611499"
```

- [ ] **Step 2: Run to verify failure**

```
pytest app/tests/test_google_analytics_router.py::test_refresh_busts_cache_then_returns_fresh -v
```
Expected: FAIL (route 404).

- [ ] **Step 3: Add the route**

Append to `app/routers/google_analytics.py`:

```python
@router.post("/refresh", response_model=PropertyOverviewResponse)
async def refresh_overview(
    property_id: str,
    ga_service: GoogleAnalyticsServiceDep,
    _: CurrentAdminDep,
    time_range: str = "7d",
):
    _require_enabled()
    data = await ga_service.get_property_overview(
        property_id, time_range, force_refresh=True
    )
    return PropertyOverviewResponse(**data)
```

- [ ] **Step 4: Run tests**

```
pytest app/tests/test_google_analytics_router.py -v
```
Expected: all PASS.

- [ ] **Step 5: Lint check and full test suite smoke**

```
make lint-check
pytest app/tests/ -v
```
Expected: both clean.

- [ ] **Step 6: Commit**

```bash
git add app/routers/google_analytics.py app/tests/test_google_analytics_router.py
git commit -m "feat(ga-router): add /refresh endpoint to bust cache for a property+range"
```

---

## Task 13: GCP setup script

**Files:**
- Create: `scripts/setup_ga_access.sh`

- [ ] **Step 1: Create the script**

```bash
#!/usr/bin/env bash
# Sets up Google Analytics Data API access for the admin dashboard.
# Idempotent: safe to re-run.
#
# Usage:
#   ./scripts/setup_ga_access.sh                            # Cloud-Run-only setup
#   ./scripts/setup_ga_access.sh user@example.com           # + local dev access

set -euo pipefail

PROJECT_ID="sb-gcp-project-01"
GA_SA_NAME="ga-reader"
GA_SA_EMAIL="${GA_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
CLOUD_RUN_SA="379507182035-compute@developer.gserviceaccount.com"
DEV_EMAIL="${1:-}"
GA_PROPERTY_IDS=("506611499" "448469065")

echo "▶ Configuring project: ${PROJECT_ID}"
gcloud config set project "${PROJECT_ID}" --quiet

echo "▶ Enabling Google Analytics Data API (skips if already enabled)"
if gcloud services list --enabled --filter="name:analyticsdata.googleapis.com" \
    --format="value(name)" | grep -q "analyticsdata"; then
    echo "   already enabled."
else
    gcloud services enable analyticsdata.googleapis.com
fi

echo "▶ Creating service account ${GA_SA_EMAIL} (skips if exists)"
if gcloud iam service-accounts describe "${GA_SA_EMAIL}" >/dev/null 2>&1; then
    echo "   already exists."
else
    gcloud iam service-accounts create "${GA_SA_NAME}" \
        --display-name="GA Data API reader for admin dashboard" \
        --description="Used by the Sunbird admin dashboard to read GA4 reports via impersonation."
fi

echo "▶ Granting Cloud Run SA (${CLOUD_RUN_SA}) tokenCreator on ${GA_SA_EMAIL}"
gcloud iam service-accounts add-iam-policy-binding "${GA_SA_EMAIL}" \
    --member="serviceAccount:${CLOUD_RUN_SA}" \
    --role="roles/iam.serviceAccountTokenCreator" \
    --condition=None \
    --quiet

if [[ -n "${DEV_EMAIL}" ]]; then
    echo "▶ Granting developer (${DEV_EMAIL}) tokenCreator on ${GA_SA_EMAIL}"
    gcloud iam service-accounts add-iam-policy-binding "${GA_SA_EMAIL}" \
        --member="user:${DEV_EMAIL}" \
        --role="roles/iam.serviceAccountTokenCreator" \
        --condition=None \
        --quiet
fi

cat <<EOF

──────────────────────────────────────────────────────────────
Manual step — grant GA property access (one-time per property)
──────────────────────────────────────────────────────────────
For each of these GA4 properties:
$(printf '  - %s\n' "${GA_PROPERTY_IDS[@]}")

  1. Open https://analytics.google.com
  2. Admin → Property Access Management
  3. Add:      ${GA_SA_EMAIL}
     Role:     Viewer

──────────────────────────────────────────────────────────────
Verify locally with impersonated credentials:
──────────────────────────────────────────────────────────────
  gcloud auth application-default login
  gcloud config set auth/impersonate_service_account ${GA_SA_EMAIL}
  # then run the backend; BetaAnalyticsDataClient will pick up impersonated ADC.

Set these Cloud Run env vars to enable the feature:
  GA_IMPERSONATION_TARGET=${GA_SA_EMAIL}
  GA_PROPERTIES=$(IFS=,; echo "${GA_PROPERTY_IDS[*]/%/:NAME_HERE}")

EOF
echo "▶ Done."
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x scripts/setup_ga_access.sh
```

- [ ] **Step 3: Dry-run / syntax check**

```bash
bash -n scripts/setup_ga_access.sh
```
Expected: no output, exit 0.

- [ ] **Step 4: Commit**

```bash
git add scripts/setup_ga_access.sh
git commit -m "feat(scripts): add idempotent GA service-account setup script"
```

---

## Task 14: Operator runbook

**Files:**
- Create: `docs/google-analytics.md`

- [ ] **Step 1: Create the runbook**

```markdown
# Google Analytics Integration — Operator Runbook

## What this feature does

Surfaces GA4 data for Sunflower (property `506611499`) and Sunbird Speech
(property `448469065`) on the admin page `/admin/google-analytics`.
Data is fetched from the Google Analytics Data API v1beta with a 1-hour
in-memory cache per Cloud Run instance.

## One-time GCP setup

```bash
./scripts/setup_ga_access.sh                          # Cloud-Run-only
./scripts/setup_ga_access.sh you@sunbird.ai           # + grant yourself local impersonation rights
```

The script is idempotent. It:
1. Enables `analyticsdata.googleapis.com` on `sb-gcp-project-01`.
2. Creates the `ga-reader@sb-gcp-project-01.iam.gserviceaccount.com` SA.
3. Grants the Cloud Run compute SA (`379507182035-compute@...`) the
   `roles/iam.serviceAccountTokenCreator` role on `ga-reader`.
4. Optionally grants the same role to a developer user principal.

## One-time GA property grant (manual)

For each GA4 property (506611499, 448469065):
1. analytics.google.com → **Admin** → **Property Access Management**
2. Add `ga-reader@sb-gcp-project-01.iam.gserviceaccount.com`
3. Role: **Viewer**

## Environment variables

| Variable | Example | Purpose |
|---|---|---|
| `GA_IMPERSONATION_TARGET` | `ga-reader@sb-gcp-project-01.iam.gserviceaccount.com` | Target SA for impersonation |
| `GA_PROPERTIES` | `506611499:Sunflower,448469065:Sunbird Speech` | Property allowlist + display names |
| `GA_CACHE_TTL_SECONDS` | `3600` | Cache TTL (default 1h) |
| `CACHE_BACKEND` | `memory` | `memory` or `upstash` (see `app/services/cache/README.md`) |

When `GA_IMPERSONATION_TARGET` or `GA_PROPERTIES` is missing/empty, the
feature returns HTTP 503 from `/api/admin/google-analytics/*` endpoints
and the frontend shows "not configured".

## Local development

```bash
gcloud auth application-default login
gcloud config set auth/impersonate_service_account \
  ga-reader@sb-gcp-project-01.iam.gserviceaccount.com
cp .env.example .env  # ensure the 4 env vars above are set
uvicorn app.api:app --reload
```

## Debugging

- **403 / permission denied from GA** — the `ga-reader` SA is missing
  Viewer access on the property; re-check Property Access Management.
- **429 / quota** — either the GA Data API quota was exceeded (rare) or
  multiple Cloud Run instances missed the cache simultaneously. Raise
  `GA_CACHE_TTL_SECONDS` or switch to a shared cache (Upstash).
- **"Google Analytics is not configured" (503)** — env vars missing in
  Cloud Run.
- **Empty data for new property** — GA ingestion lags 4–24h; verify by
  looking at the same range in the GA web UI.
```

- [ ] **Step 2: Commit**

```bash
git add docs/google-analytics.md
git commit -m "docs: add GA integration operator runbook"
```

---

## Task 15: Frontend — types and data-fetching hook

**Files:**
- Create: `frontend/src/hooks/useGoogleAnalytics.ts`

- [ ] **Step 1: Create the hook file**

```typescript
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

export interface GAProperty {
  id: string;
  name: string;
}

export interface GATrafficSeries {
  labels: string[];
  active_users: number[];
  new_users: number[];
  sessions: number[];
  engaged_sessions: number[];
  engagement_rate: number[];
  avg_session_duration: number[];
  bounce_rate: number[];
}

export interface GATopPage {
  path: string;
  title: string;
  views: number;
  users: number;
  avg_duration: number;
}

export interface GAPlatformRow {
  label: string;
  users: number;
  sessions: number;
}

export interface GAPlatforms {
  device: GAPlatformRow[];
  os: GAPlatformRow[];
  browser: GAPlatformRow[];
}

export interface GAGeoRow {
  country: string;
  city: string;
  users: number;
  sessions: number;
}

export interface GAEventRow {
  name: string;
  count: number;
  users: number;
}

export interface GAOverview {
  property_id: string;
  property_name: string;
  time_range: string;
  cached_until: string;
  traffic: GATrafficSeries;
  top_pages: GATopPage[];
  platforms: GAPlatforms;
  geography: GAGeoRow[];
  events: GAEventRow[];
  partial: boolean;
  failed_reports: string[];
}

const BASE = '/api/admin/google-analytics';

export function useGAProperties() {
  const [properties, setProperties] = useState<GAProperty[]>([]);
  const [loading, setLoading] = useState(true);
  const [notConfigured, setNotConfigured] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await axios.get(`${BASE}/properties`);
        if (!cancelled) setProperties(data.properties);
      } catch (err: any) {
        if (err?.response?.status === 503) {
          if (!cancelled) setNotConfigured(true);
        } else {
          toast.error('Failed to load GA properties');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return { properties, loading, notConfigured };
}

export function useGAOverview(propertyId: string, timeRange: string) {
  const [data, setData] = useState<GAOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchOverview = useCallback(
    async (force = false) => {
      if (!propertyId) return;
      setLoading(true);
      setError(null);
      try {
        const url = force ? `${BASE}/refresh` : `${BASE}/overview`;
        const method = force ? axios.post : axios.get;
        const { data: payload } = await method(url, {
          params: { property_id: propertyId, time_range: timeRange },
        });
        setData(payload);
      } catch (err: any) {
        const msg = err?.response?.data?.detail || 'Failed to load analytics';
        setError(typeof msg === 'string' ? msg : 'Failed to load analytics');
        toast.error(typeof msg === 'string' ? msg : 'Failed to load analytics');
      } finally {
        setLoading(false);
      }
    },
    [propertyId, timeRange],
  );

  useEffect(() => {
    fetchOverview(false);
  }, [fetchOverview]);

  return {
    data,
    loading,
    error,
    refresh: () => fetchOverview(true),
  };
}
```

- [ ] **Step 2: Type-check**

```
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useGoogleAnalytics.ts
git commit -m "feat(frontend): add GA types and data-fetching hook"
```

---

## Task 16: Frontend — TrafficChart + TopPagesTable components

**Files:**
- Create: `frontend/src/components/ga/TrafficChart.tsx`
- Create: `frontend/src/components/ga/TopPagesTable.tsx`

- [ ] **Step 1: Create `frontend/src/components/ga/TrafficChart.tsx`**

```tsx
import { Line } from 'react-chartjs-2';
import type { GATrafficSeries } from '../../hooks/useGoogleAnalytics';

interface Props {
  series: GATrafficSeries;
}

export default function TrafficChart({ series }: Props) {
  const data = {
    labels: series.labels,
    datasets: [
      {
        label: 'Active users',
        data: series.active_users,
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59,130,246,0.15)',
        tension: 0.4,
      },
      {
        label: 'New users',
        data: series.new_users,
        borderColor: '#10b981',
        backgroundColor: 'rgba(16,185,129,0.1)',
        tension: 0.4,
      },
      {
        label: 'Sessions',
        data: series.sessions,
        borderColor: '#f59e0b',
        backgroundColor: 'rgba(245,158,11,0.1)',
        tension: 0.4,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'top' as const } },
    interaction: { mode: 'index' as const, intersect: false },
    scales: {
      y: { beginAtZero: true, grid: { color: 'rgba(156,163,175,0.1)' } },
      x: { grid: { display: false } },
    },
  };

  return (
    <div className="h-[300px]">
      <Line data={data} options={options} />
    </div>
  );
}
```

- [ ] **Step 2: Create `frontend/src/components/ga/TopPagesTable.tsx`**

```tsx
import type { GATopPage } from '../../hooks/useGoogleAnalytics';

interface Props {
  pages: GATopPage[];
}

export default function TopPagesTable({ pages }: Props) {
  if (!pages.length) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">No page views in this range.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 dark:border-white/10 text-left">
            <th className="py-2 px-3 font-medium text-gray-500 dark:text-gray-400">Page</th>
            <th className="py-2 px-3 font-medium text-gray-500 dark:text-gray-400 text-right">Views</th>
            <th className="py-2 px-3 font-medium text-gray-500 dark:text-gray-400 text-right">Users</th>
            <th className="py-2 px-3 font-medium text-gray-500 dark:text-gray-400 text-right">Avg duration</th>
          </tr>
        </thead>
        <tbody>
          {pages.map((p) => (
            <tr
              key={p.path}
              className="border-b border-gray-100 dark:border-white/5 hover:bg-gray-50 dark:hover:bg-white/5"
            >
              <td className="py-2 px-3">
                <div className="font-medium text-gray-900 dark:text-white">{p.title || p.path}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">{p.path}</div>
              </td>
              <td className="py-2 px-3 text-right text-gray-900 dark:text-white">
                {p.views.toLocaleString()}
              </td>
              <td className="py-2 px-3 text-right text-gray-900 dark:text-white">
                {p.users.toLocaleString()}
              </td>
              <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">
                {p.avg_duration.toFixed(1)}s
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ga/TrafficChart.tsx frontend/src/components/ga/TopPagesTable.tsx
git commit -m "feat(frontend): add GA traffic chart and top pages table"
```

---

## Task 17: Frontend — Platform, Geo, Events components

**Files:**
- Create: `frontend/src/components/ga/PlatformBreakdown.tsx`
- Create: `frontend/src/components/ga/GeoBreakdown.tsx`
- Create: `frontend/src/components/ga/EventsTable.tsx`

- [ ] **Step 1: `frontend/src/components/ga/PlatformBreakdown.tsx`**

```tsx
import type { GAPlatforms, GAPlatformRow } from '../../hooks/useGoogleAnalytics';

interface Props {
  platforms: GAPlatforms;
}

function PlatformList({ title, rows }: { title: string; rows: GAPlatformRow[] }) {
  const total = rows.reduce((acc, r) => acc + r.users, 0);
  return (
    <div>
      <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">{title}</h4>
      {rows.length === 0 ? (
        <p className="text-xs text-gray-500">No data.</p>
      ) : (
        <ul className="space-y-1">
          {rows.map((r) => {
            const pct = total ? ((r.users / total) * 100).toFixed(1) : '0';
            return (
              <li key={r.label} className="flex items-center justify-between text-sm">
                <span className="text-gray-700 dark:text-gray-300">{r.label}</span>
                <span className="text-gray-900 dark:text-white font-medium">
                  {r.users.toLocaleString()}{' '}
                  <span className="text-xs text-gray-500">({pct}%)</span>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default function PlatformBreakdown({ platforms }: Props) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      <PlatformList title="Device" rows={platforms.device} />
      <PlatformList title="Operating system" rows={platforms.os} />
      <PlatformList title="Browser" rows={platforms.browser} />
    </div>
  );
}
```

- [ ] **Step 2: `frontend/src/components/ga/GeoBreakdown.tsx`**

```tsx
import type { GAGeoRow } from '../../hooks/useGoogleAnalytics';

interface Props {
  rows: GAGeoRow[];
}

export default function GeoBreakdown({ rows }: Props) {
  if (!rows.length) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">No geographic data.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 dark:border-white/10 text-left">
            <th className="py-2 px-3 font-medium text-gray-500 dark:text-gray-400">Country</th>
            <th className="py-2 px-3 font-medium text-gray-500 dark:text-gray-400">City</th>
            <th className="py-2 px-3 font-medium text-gray-500 dark:text-gray-400 text-right">Users</th>
            <th className="py-2 px-3 font-medium text-gray-500 dark:text-gray-400 text-right">Sessions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={`${r.country}-${r.city}`}
              className="border-b border-gray-100 dark:border-white/5 hover:bg-gray-50 dark:hover:bg-white/5"
            >
              <td className="py-2 px-3 text-gray-900 dark:text-white">{r.country || '—'}</td>
              <td className="py-2 px-3 text-gray-700 dark:text-gray-300">{r.city || '—'}</td>
              <td className="py-2 px-3 text-right text-gray-900 dark:text-white">
                {r.users.toLocaleString()}
              </td>
              <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">
                {r.sessions.toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 3: `frontend/src/components/ga/EventsTable.tsx`**

```tsx
import type { GAEventRow } from '../../hooks/useGoogleAnalytics';

interface Props {
  events: GAEventRow[];
}

export default function EventsTable({ events }: Props) {
  if (!events.length) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">No events in this range.</p>;
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-gray-200 dark:border-white/10 text-left">
          <th className="py-2 px-3 font-medium text-gray-500 dark:text-gray-400">Event</th>
          <th className="py-2 px-3 font-medium text-gray-500 dark:text-gray-400 text-right">Count</th>
          <th className="py-2 px-3 font-medium text-gray-500 dark:text-gray-400 text-right">Users</th>
        </tr>
      </thead>
      <tbody>
        {events.map((e) => (
          <tr
            key={e.name}
            className="border-b border-gray-100 dark:border-white/5 hover:bg-gray-50 dark:hover:bg-white/5"
          >
            <td className="py-2 px-3 text-gray-900 dark:text-white font-mono text-xs">
              {e.name}
            </td>
            <td className="py-2 px-3 text-right text-gray-900 dark:text-white">
              {e.count.toLocaleString()}
            </td>
            <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">
              {e.users.toLocaleString()}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 4: Type-check**

```
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ga
git commit -m "feat(frontend): add GA platform, geo, and events components"
```

---

## Task 18: Frontend — GoogleAnalytics page

**Files:**
- Create: `frontend/src/pages/GoogleAnalytics.tsx`

- [ ] **Step 1: Create the page**

```tsx
import { useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Activity, Clock, TrendingUp, Users as UsersIcon, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { Skeleton } from '../components/ui/Skeleton';
import ChartCard from '../components/ChartCard';
import MetricCard from '../components/MetricCard';
import { useGAOverview, useGAProperties } from '../hooks/useGoogleAnalytics';
import TrafficChart from '../components/ga/TrafficChart';
import TopPagesTable from '../components/ga/TopPagesTable';
import PlatformBreakdown from '../components/ga/PlatformBreakdown';
import GeoBreakdown from '../components/ga/GeoBreakdown';
import EventsTable from '../components/ga/EventsTable';

const TIME_RANGES = [
  { label: 'Last 24h', value: '24h' },
  { label: 'Last 7 days', value: '7d' },
  { label: 'Last 30 days', value: '30d' },
  { label: 'Last 60 days', value: '60d' },
  { label: 'Last 90 days', value: '90d' },
];

export default function GoogleAnalytics() {
  const { properties, loading: propsLoading, notConfigured } = useGAProperties();
  const [searchParams, setSearchParams] = useSearchParams();

  const propertyId = searchParams.get('property') || '';
  const timeRange = searchParams.get('range') || '7d';

  // Default to first property once loaded
  useEffect(() => {
    if (!propertyId && properties.length > 0) {
      setSearchParams(
        { property: properties[0].id, range: timeRange },
        { replace: true },
      );
    }
  }, [properties, propertyId, timeRange, setSearchParams]);

  const { data, loading, error, refresh } = useGAOverview(propertyId, timeRange);

  const totals = useMemo(() => {
    if (!data) return null;
    const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);
    const avg = (xs: number[]) => (xs.length ? sum(xs) / xs.length : 0);
    return {
      users: sum(data.traffic.active_users),
      sessions: sum(data.traffic.sessions),
      engagementRate: avg(data.traffic.engagement_rate),
      avgSessionSec: avg(data.traffic.avg_session_duration),
    };
  }, [data]);

  if (notConfigured) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500 dark:text-gray-400">
          Google Analytics is not configured. See <code>docs/google-analytics.md</code>.
        </p>
      </div>
    );
  }

  if (propsLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-10 w-full max-w-xl" />
        <Skeleton className="h-[400px] w-full rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Google Analytics</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Site & app analytics for Sunbird properties.
          </p>
        </div>
        <button
          onClick={() => {
            refresh();
            toast.info('Refreshing from Google Analytics…');
          }}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors text-sm font-medium"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap gap-3 items-center">
        <select
          value={propertyId}
          onChange={(e) =>
            setSearchParams({ property: e.target.value, range: timeRange })
          }
          className="px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-secondary text-sm"
        >
          {properties.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>

        <select
          value={timeRange}
          onChange={(e) =>
            setSearchParams({ property: propertyId, range: e.target.value })
          }
          className="px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-secondary text-sm"
        >
          {TIME_RANGES.map((r) => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </select>

        {data && (
          <span className="text-xs text-gray-500 dark:text-gray-400 ml-auto">
            Cached until {new Date(data.cached_until).toLocaleTimeString()}
          </span>
        )}
      </div>

      {loading && !data && (
        <Skeleton className="h-[400px] w-full rounded-xl" />
      )}

      {error && !data && (
        <div className="p-4 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 text-sm">
          {error}
        </div>
      )}

      {data && totals && (
        <>
          {data.partial && (
            <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 text-amber-800 dark:text-amber-200 text-sm">
              Some reports failed to load: {data.failed_reports.join(', ')}.
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <MetricCard label="Users" value={totals.users.toLocaleString()} icon={UsersIcon} color="bg-blue-500" />
            <MetricCard label="Sessions" value={totals.sessions.toLocaleString()} icon={Activity} color="bg-orange-500" />
            <MetricCard label="Engagement" value={`${(totals.engagementRate * 100).toFixed(1)}%`} icon={TrendingUp} color="bg-purple-500" />
            <MetricCard label="Avg session" value={`${totals.avgSessionSec.toFixed(0)}s`} icon={Clock} color="bg-green-500" />
          </div>

          <ChartCard
            title="Traffic over time"
            description={`Active users, new users, sessions for ${data.property_name}`}
            className="h-[400px]"
          >
            <TrafficChart series={data.traffic} />
          </ChartCard>

          <div className="bg-white dark:bg-secondary rounded-xl shadow-md border border-gray-200 dark:border-white/5 p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Top pages</h3>
            <TopPagesTable pages={data.top_pages} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white dark:bg-secondary rounded-xl shadow-md border border-gray-200 dark:border-white/5 p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Platforms</h3>
              <PlatformBreakdown platforms={data.platforms} />
            </div>

            <div className="bg-white dark:bg-secondary rounded-xl shadow-md border border-gray-200 dark:border-white/5 p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Geography</h3>
              <GeoBreakdown rows={data.geography} />
            </div>
          </div>

          <div className="bg-white dark:bg-secondary rounded-xl shadow-md border border-gray-200 dark:border-white/5 p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Top events</h3>
            <EventsTable events={data.events} />
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```
cd frontend && npx tsc --noEmit
```
Expected: no errors. If `ChartCard` or `MetricCard` props don't match what's imported, adjust the import paths / component usage to match the existing `AdminAnalytics.tsx`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/GoogleAnalytics.tsx
git commit -m "feat(frontend): add Google Analytics admin page"
```

---

## Task 19: Route + sidebar wiring + build verification

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Layout.tsx`

- [ ] **Step 1: Add the route in `frontend/src/App.tsx`**

Add the import near the other page imports:

```typescript
import GoogleAnalytics from './pages/GoogleAnalytics';
```

Add the route below the `/admin/analytics` route:

```tsx
<Route
  path="/admin/google-analytics"
  element={
    <RequireAuth>
      <Layout>
        <PageTitle title="Google Analytics">
          <GoogleAnalytics />
        </PageTitle>
      </Layout>
    </RequireAuth>
  }
/>
```

- [ ] **Step 2: Add the sidebar link in `frontend/src/components/Layout.tsx`**

Find the `navigation` array around line 25:

```typescript
  const navigation = [
    ...(isAdmin
      ? [{ name: 'Analytics', href: '/admin/analytics', icon: BarChart3 }]
      : [{ name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard }]),
    { name: 'API Keys', href: '/keys', icon: Key },
    { name: 'Account', href: '/account', icon: Settings },
  ];
```

Add the GA entry immediately after the admin "Analytics" entry. First, add the icon import at the top of the file:

```typescript
import { LineChart } from 'lucide-react';
```

(Append `LineChart` to the existing lucide-react imports rather than duplicating the import line.)

Then replace the `navigation` block:

```typescript
  const navigation = [
    ...(isAdmin
      ? [
          { name: 'Analytics', href: '/admin/analytics', icon: BarChart3 },
          { name: 'Google Analytics', href: '/admin/google-analytics', icon: LineChart },
        ]
      : [{ name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard }]),
    { name: 'API Keys', href: '/keys', icon: Key },
    { name: 'Account', href: '/account', icon: Settings },
  ];
```

- [ ] **Step 3: Lint + build + audit**

```
cd frontend
npm run lint
npm run build
npm audit
```
Expected:
- Lint: clean
- Build: succeeds, writes to `../app/static/react_build/`
- Audit: no new high/critical vulnerabilities. The newly-added deps come from Task 1 (backend) so this should be unchanged from before.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/Layout.tsx
git commit -m "feat(frontend): mount /admin/google-analytics route and sidebar link"
```

---

## Task 20: Final verification — Definition of Done

- [ ] **Step 1: Run the full backend suite**

```
pytest app/tests/ -v
```
Expected: all tests pass (no regressions in pre-existing tests).

- [ ] **Step 2: Backend lint**

```
make lint-check
```
Expected: clean.

- [ ] **Step 3: Frontend build + lint**

```
cd frontend
npm run lint
npm run build
```
Expected: clean.

- [ ] **Step 4: `npm audit`**

```
cd frontend
npm audit
```
Expected: no new high/critical vulnerabilities.

- [ ] **Step 5: Local smoke test (requires GA access granted)**

1. Run `./scripts/setup_ga_access.sh $(git config user.email)`.
2. Add `ga-reader@sb-gcp-project-01.iam.gserviceaccount.com` as Viewer on both GA4 properties (via GA admin UI).
3. Locally:
   ```
   gcloud auth application-default login
   gcloud config set auth/impersonate_service_account \
     ga-reader@sb-gcp-project-01.iam.gserviceaccount.com
   export GA_IMPERSONATION_TARGET=ga-reader@sb-gcp-project-01.iam.gserviceaccount.com
   export GA_PROPERTIES="506611499:Sunflower,448469065:Sunbird Speech"
   uvicorn app.api:app --reload
   ```
4. In another terminal: `cd frontend && npm run dev`.
5. Log in as an admin user, navigate to `/admin/google-analytics`.
6. Switch between Sunflower and Sunbird Speech. Switch between 24h / 7d / 30d / 60d / 90d. Click Refresh.
7. Confirm all five sections render data (or show "No data" if the property truly has none).

- [ ] **Step 6: Final commit (if anything updated from smoke test)**

If no code changes are needed, skip this step. Otherwise commit with a focused message.

---

## Self-Review Notes

- **Spec coverage:** Every section of the spec maps to at least one task — see mapping below.
  - Spec §4 (GCP setup) → Task 13 + Task 14
  - Spec §5.1 (integration client) → Task 4
  - Spec §5.2 (cache) → Tasks 2, 3
  - Spec §5.3 (service) → Tasks 6, 7, 8, 9
  - Spec §5.4 (router) → Tasks 10, 11, 12
  - Spec §5.5 (schemas) → Task 5
  - Spec §5.6 (deps) → Tasks 3, 9
  - Spec §6 (frontend) → Tasks 15, 16, 17, 18, 19
  - Spec §7 (config) → Task 1
  - Spec §8 (error handling) → Tasks 8, 10, 11, 12
  - Spec §9 (testing) → Tasks 2, 4, 5, 6, 7, 8, 10, 11, 12
  - Spec §11 (rollout) → Task 20 smoke test
- **Placeholders:** None. Every code step contains concrete code and every command step contains concrete commands.
- **Type/naming consistency:**
  - Cache protocol `CacheBackend` used consistently.
  - Report names constant `REPORT_NAMES = ("traffic","pages","platforms","geography","events")` matches the aggregator's label tuple.
  - Cache key format `ga:{property_id}:{report_name}:{time_range}` used in all services and in the router force-refresh flow.
  - Hook names (`useGAProperties`, `useGAOverview`) match import sites.
