# Google Analytics Integration for Admin Dashboard — Design

**Date:** 2026-04-19
**Status:** Draft — pending user review
**Owner:** Patrick Walukagga

## 1. Goals

Surface Google Analytics 4 (GA4) data for Sunbird's two product properties inside the existing admin area, as a complement to the current API-usage dashboard at [AdminAnalytics.tsx](../../../frontend/src/pages/AdminAnalytics.tsx).

**GA4 properties in scope:**
- Sunflower — property ID `506611499`
- Sunbird Speech — property ID `448469065`

**GCP project:** `sb-gcp-project-01`

**Metrics surfaced (v1):**
- Traffic / audience — active users, new users, sessions, engaged sessions, engagement rate, avg session duration, bounce rate
- Content — top pages (pagePath, views, users, avg time)
- Platform — device category, OS, browser breakdown
- Geography — country + city breakdown (table only; no map)
- Events — top custom events and their counts

Retention, real-time, acquisition channels, and BigQuery-export paths are **out of scope** for v1.

## 2. Non-goals / deferred

- BigQuery export integration
- Geography map visualisation
- Realtime API (`runRealtimeReport`)
- Retention / cohort reports
- CSV export for GA reports
- Multi-property side-by-side comparison view

## 3. Architecture

### 3.1 Data flow

```
Admin browser
    │ GET /api/admin/google-analytics/overview?property_id=506611499&time_range=7d
    ▼
FastAPI router (admin-guarded via get_current_admin)
    │ cache key = (property_id, report_name, time_range)
    ▼
GoogleAnalyticsService ──► CacheBackend ──► HIT? return cached payload
    │                            │
    │ (miss)                     ▼ SET with 1h TTL
    ▼
GoogleAnalyticsClient (integration layer)
    │ impersonated_credentials → BetaAnalyticsDataClient
    ▼
Google Analytics Data API v1beta
```

### 3.2 New files

| File | Purpose |
|------|---------|
| `app/integrations/google_analytics.py` | GA Data API wrapper + impersonation |
| `app/services/google_analytics_service.py` | Business logic, report orchestration, cache use, response shaping |
| `app/services/cache/__init__.py` | `CacheBackend` protocol + factory |
| `app/services/cache/in_memory.py` | `InMemoryTTLCache` using `cachetools.TTLCache` |
| `app/services/cache/README.md` | Docs for swapping to Upstash/Redis |
| `app/routers/google_analytics.py` | `/api/admin/google-analytics/*` routes |
| `app/schemas/google_analytics.py` | Pydantic response models |
| `scripts/setup_ga_access.sh` | GCP setup script |
| `docs/google-analytics.md` | Operator runbook |
| `frontend/src/pages/GoogleAnalytics.tsx` | Admin page |
| `frontend/src/hooks/useGoogleAnalytics.ts` | Data-fetching hooks |
| `frontend/src/components/ga/TrafficChart.tsx` | Traffic line chart |
| `frontend/src/components/ga/TopPagesTable.tsx` | Top pages table |
| `frontend/src/components/ga/PlatformBreakdown.tsx` | Device / OS / browser |
| `frontend/src/components/ga/GeoBreakdown.tsx` | Country + city table |
| `frontend/src/components/ga/EventsTable.tsx` | Top events table |

### 3.3 Updated files

- `app/api.py` — include new router
- `app/deps.py` — register `GoogleAnalyticsServiceDep`
- `app/core/config.py` — new env vars
- `requirements.txt` — add `google-analytics-data`, `cachetools`
- `frontend/src/App.tsx` — new protected route `/admin/google-analytics`
- `frontend/src/components/Layout.tsx` — sidebar link under admin section

## 4. GCP setup

### 4.1 `scripts/setup_ga_access.sh`

Idempotent bash script driven by these defaults:

```bash
PROJECT_ID="sb-gcp-project-01"
GA_SA_NAME="ga-reader"
GA_SA_EMAIL="${GA_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
CLOUD_RUN_SA="379507182035-compute@developer.gserviceaccount.com"
DEV_EMAIL=""   # optional; pass as $1 to grant dev impersonation
GA_PROPERTY_IDS=("506611499" "448469065")
```

**Script steps (each idempotent — check before create):**
1. `gcloud config set project sb-gcp-project-01`
2. Enable the API: `gcloud services enable analyticsdata.googleapis.com` (skip if already enabled)
3. Create the `ga-reader` service account (skip if exists)
4. Grant Cloud Run SA token-creator on `ga-reader`:
   `roles/iam.serviceAccountTokenCreator` → `serviceAccount:$CLOUD_RUN_SA`
5. If `DEV_EMAIL` is provided, grant the same role to `user:$DEV_EMAIL` for local impersonation
6. Print manual instructions for the GA-side grant (GA property access is managed inside the GA admin UI, not IAM):
   > For each property (506611499, 448469065):
   > 1. analytics.google.com → Admin → Property Access Management
   > 2. Add `ga-reader@sb-gcp-project-01.iam.gserviceaccount.com` with role **Viewer**
7. Print verification commands:
   ```bash
   gcloud auth application-default login
   gcloud config set auth/impersonate_service_account ga-reader@sb-gcp-project-01.iam.gserviceaccount.com
   ```

### 4.2 Runtime credentials

Production (Cloud Run): the container runs as `379507182035-compute@developer.gserviceaccount.com`. The integration layer uses `google.auth.default()` to pick up those credentials, wraps them in `google.auth.impersonated_credentials.Credentials` targeting `ga-reader@...`, and passes the result to `BetaAnalyticsDataClient(credentials=...)`. No JSON key files.

Local development: same code path. Developer runs `gcloud auth application-default login` + `gcloud config set auth/impersonate_service_account ga-reader@...` once, and the library picks up the impersonated ADC automatically.

## 5. Backend components

### 5.1 `app/integrations/google_analytics.py`

```python
class GoogleAnalyticsClient:
    def __init__(self, target_sa: str, scopes: list[str] | None = None):
        self._target_sa = target_sa
        source_creds, _ = google.auth.default()
        self._creds = impersonated_credentials.Credentials(
            source_credentials=source_creds,
            target_principal=target_sa,
            target_scopes=scopes or ["https://www.googleapis.com/auth/analytics.readonly"],
            lifetime=3600,
        )
        self._client = BetaAnalyticsDataClient(credentials=self._creds)

    async def run_report(
        self,
        property_id: str,
        dimensions: list[str],
        metrics: list[str],
        start_date: str,
        end_date: str = "today",
        limit: int | None = None,
        order_bys: list | None = None,
    ) -> dict:
        ...
```

The underlying `run_report` call is synchronous gRPC; we wrap it with `asyncio.to_thread` to keep the FastAPI event loop unblocked. The wrapper returns a normalised dict `{"dimension_headers": [...], "metric_headers": [...], "rows": [...]}` so the service layer never sees proto objects.

Singleton factory `get_google_analytics_client()` matching the pattern in `.claude/rules/routers.md`.

### 5.2 `app/services/cache/`

```python
# __init__.py
class CacheBackend(Protocol):
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl_seconds: int) -> None: ...
    async def delete(self, key: str) -> None: ...

def get_cache_backend() -> CacheBackend:
    # Returns InMemoryTTLCache when settings.cache_backend == "memory"
    # Swap to UpstashRedisCache when settings.cache_backend == "upstash"
```

```python
# in_memory.py
class InMemoryTTLCache(CacheBackend):
    def __init__(self, maxsize: int = 256):
        self._buckets: dict[int, TTLCache] = {}
        self._maxsize = maxsize
        self._lock = asyncio.Lock()
    # get/set/delete wrap cachetools.TTLCache under the asyncio.Lock
```

**Upstash migration path** (documented in `README.md`): install `upstash-redis`, add `UpstashRedisCache(CacheBackend)` using `UPSTASH_REDIS_REST_URL` + `UPSTASH_REDIS_REST_TOKEN`, set `CACHE_BACKEND=upstash`. No other code changes needed.

### 5.3 `app/services/google_analytics_service.py`

Five report methods:

| Method | Dimensions | Metrics |
|---|---|---|
| `get_traffic_overview(property_id, time_range)` | `date` | `activeUsers`, `newUsers`, `sessions`, `engagedSessions`, `engagementRate`, `averageSessionDuration`, `bounceRate` |
| `get_top_pages(property_id, time_range, limit=10)` | `pagePath`, `pageTitle` | `screenPageViews`, `activeUsers`, `averageSessionDuration` |
| `get_platform_breakdown(property_id, time_range)` | `deviceCategory`, `operatingSystem`, `browser` | `activeUsers`, `sessions` |
| `get_geo_breakdown(property_id, time_range, limit=20)` | `country`, `city` | `activeUsers`, `sessions` |
| `get_top_events(property_id, time_range, limit=15)` | `eventName` | `eventCount`, `totalUsers` |

Plus an aggregator `get_property_overview(property_id, time_range, force_refresh=False)` that runs all five concurrently via `asyncio.gather(..., return_exceptions=True)` and returns a single `PropertyOverviewResponse`.

**Time range mapping** (`_parse_time_range`):
- `"24h"` → `("yesterday", "today")`
- `"7d"` → `("7daysAgo", "today")`
- `"30d"` → `("30daysAgo", "today")`
- `"60d"` → `("60daysAgo", "today")`
- `"90d"` → `("90daysAgo", "today")`

GA data lags 4–24h, so sub-day buckets are not useful.

**Property allowlist** — loaded from `settings.ga_properties` (env-var driven). Any request with an unlisted `property_id` raises `BadRequestError`. This also contains blast radius if an admin token leaked.

**Cache key format**: `f"ga:{property_id}:{report_name}:{time_range}"`. TTL from `settings.ga_cache_ttl_seconds` (default 3600). Each of the 5 reports gets its own entry; the aggregator composes them.

**Payload wrapping** — the cached value is `{"cached_at": <iso8601>, "data": <report dict>}`, so `PropertyOverviewResponse.cached_until` can be computed as `min(cached_at across all 5 reports) + ttl`. This gives the frontend an honest expiry even when individual reports were cached at different times.

**`force_refresh`** — the service defines a module-level constant `REPORT_NAMES = ("traffic", "pages", "platforms", "geography", "events")`. `force_refresh=True` iterates this list and calls `cache.delete(f"ga:{property_id}:{name}:{time_range}")` for each before refetching. This avoids needing a pattern-delete operation (which in-memory `TTLCache` doesn't support natively).

### 5.4 `app/routers/google_analytics.py`

All under `/api/admin/google-analytics`, all gated by `get_current_admin`:

| Route | Purpose |
|---|---|
| `GET /properties` | Returns `[{id, name}, ...]` for the frontend picker |
| `GET /overview?property_id=...&time_range=7d` | Aggregated 5-report response |
| `POST /refresh?property_id=...&time_range=7d` | Bust cache for one property+time_range, return fresh overview |

If `settings.ga_enabled` is false, all routes return 503 with `{detail: "Google Analytics is not configured"}`.

Per-report endpoints (`/traffic`, `/pages`, etc.) are intentionally **not** shipped in v1. Add only if the UI later needs independent refreshes per card (YAGNI).

### 5.5 `app/schemas/google_analytics.py`

Typed Pydantic v2 response models:
- `PropertyInfo {id, name}`
- `TrafficTimeSeries {labels, active_users, new_users, sessions, engaged_sessions, engagement_rate, avg_session_duration, bounce_rate}` — all lists aligned to `labels`
- `TopPageRow {path, title, views, users, avg_duration}`
- `PlatformRow {label, users, sessions}` with three variants (device, os, browser)
- `GeoRow {country, city, users, sessions}`
- `EventRow {name, count, users}`
- `PropertyOverviewResponse {property_id, property_name, time_range, cached_until, traffic, top_pages, platforms: {device, os, browser}, geography, events, partial, failed_reports}`

### 5.6 `app/deps.py`

```python
GoogleAnalyticsServiceDep = Annotated[
    GoogleAnalyticsService, Depends(get_google_analytics_service)
]
CacheBackendDep = Annotated[CacheBackend, Depends(get_cache_backend)]
```

## 6. Frontend

### 6.1 Page layout — `frontend/src/pages/GoogleAnalytics.tsx`

```
┌────────────────────────────────────────────────────────────────┐
│ Google Analytics                            [ Refresh ⟳ ]      │
│ Site & app analytics for Sunbird properties.                   │
├────────────────────────────────────────────────────────────────┤
│ [ Property ▾ Sunflower ]  [ Time range ▾ Last 7 days ]         │
│ Cached until 14:32 UTC                                         │
├────────────────────────────────────────────────────────────────┤
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│ │ Users    │ │ Sessions │ │ Engag.   │ │ Avg sess │            │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘            │
│                                                                │
│ [ Traffic over time — line chart ]                             │
│                                                                │
│ ┌──── Top pages (table) ──────────────────────────┐            │
│                                                                │
│ ┌─── Platform ──┐ ┌──── Geography (table) ───────┐             │
│                                                                │
│ ┌─── Top events (table) ─────┐                                 │
└────────────────────────────────────────────────────────────────┘
```

- **Property picker** — reuses the existing `SearchableSelect` component.
- **Time range picker** — same control style as `ChartCard`'s `showTimeSelector`. Presets: 24h, 7d, 30d, 60d, 90d.
- **Refresh button** — calls `POST /refresh`, spinner while pending, toast on result.
- **"Cached until" label** — shows `cached_until` from response so admins know when data was fetched.
- **Charts** — Chart.js + react-chartjs-2 (already in stack).

### 6.2 Hooks — `frontend/src/hooks/useGoogleAnalytics.ts`

```ts
export interface GAProperty { id: string; name: string; }
export interface GAOverview { ... /* matches PropertyOverviewResponse */ }

export function useGAProperties(): { properties: GAProperty[]; loading: boolean };
export function useGAOverview(
  propertyId: string, timeRange: string
): { data: GAOverview | null; loading: boolean; error: string | null; refresh: () => Promise<void> };
```

Same Axios + `toast` patterns as `useAdminAnalytics`. No new libraries.

### 6.3 Routing & navigation

- `App.tsx` — new protected route `/admin/google-analytics` inside `RequireAuth`.
- `Layout.tsx` — sidebar link "Google Analytics" as a sibling of "Admin Analytics" under the admin section; visible only when `user.role === "admin"`.
- URL state — `property` and `range` as query params via `useSearchParams`, default property = first in the list.

### 6.4 Loading / empty / error states

- Initial load: `Skeleton` primitives matching `AdminAnalytics.tsx`.
- No data in range: empty-state card, icon + message (e.g. "No data for Sunflower in the last 7 days.").
- API error: toast + inline banner with Retry button. Detailed reason shown (admin-only page).
- Partial success: show successful cards, inline error chip on failed cards.

## 7. Configuration

New fields on `Settings` in `app/core/config.py`:

```python
ga_impersonation_target: Optional[str] = Field(default=None)
ga_properties_raw: str = Field(default="", alias="GA_PROPERTIES")
ga_cache_ttl_seconds: int = Field(default=3600)
ga_request_timeout_seconds: int = Field(default=30)
cache_backend: str = Field(default="memory")  # memory | upstash

@property
def ga_properties(self) -> dict[str, str]:
    return dict(
        part.split(":", 1)
        for part in self.ga_properties_raw.split(",")
        if ":" in part
    )

@property
def ga_enabled(self) -> bool:
    return bool(self.ga_impersonation_target) and bool(self.ga_properties)
```

**Env vars** (documented in `docs/google-analytics.md`):
- `GA_IMPERSONATION_TARGET=ga-reader@sb-gcp-project-01.iam.gserviceaccount.com`
- `GA_PROPERTIES=506611499:Sunflower,448469065:Sunbird Speech`
- Optional: `GA_CACHE_TTL_SECONDS`, `CACHE_BACKEND`

`ga_enabled` lets the feature ship dark and be turned on later by setting env vars only.

## 8. Error handling

| Failure | Handling |
|---|---|
| `ga_enabled = False` | Router returns 503 `{detail: "Google Analytics is not configured"}`. Frontend shows "Feature not enabled" state; no retry. |
| Invalid `property_id` (not in allowlist) | `BadRequestError` (400). |
| GA API `PERMISSION_DENIED` | Log full error with `property_id`; return `ExternalServiceError` (502) with generic message. |
| GA API `RESOURCE_EXHAUSTED` | 429 with `Retry-After`; frontend shows "Rate limited". |
| GA API timeout / transient | Retry once with 1s backoff at the integration layer; if still failing, `ExternalServiceError` (502). |
| Aggregator partial failure (1 of 5) | Return successful reports; response includes `partial: true` and `failed_reports: [...]`. Frontend shows per-section error on failed cards only. |
| Impersonation fails at startup | Log loudly but don't crash. `ga_enabled` becomes effectively false via lazy credential check on first call. |

All GA errors are logged with `property_id`, `time_range`, and the GA error code. Error details are only shown inside the admin-gated page.

## 9. Testing

Follows `.claude/rules/testing.md` patterns (in-memory SQLite, `asyncio_mode = auto`).

### 9.1 Unit — `app/tests/test_google_analytics_service.py`
- Time range mapping
- Property allowlist validation
- Response shaping (fixture GA responses → expected schema)
- Cache hit / miss / refresh behaviour (fake `CacheBackend`)
- Partial-failure aggregation (mock one report to raise)

### 9.2 Unit — `app/tests/test_cache_in_memory.py`
- `set` + `get` within TTL
- `get` after TTL → None
- `delete` removes key
- Concurrent access (basic `asyncio.gather` test)

### 9.3 Integration — `app/tests/test_google_analytics_router.py`
- Admin auth required (anon → 401, non-admin → 403)
- `/properties` returns parsed list from env
- `/overview` hits service with correct params; uses monkeypatched `GoogleAnalyticsClient` returning canned fixtures
- `/refresh` busts cache then refetches
- `ga_enabled=False` → 503
- Invalid property → 400
- Partial failure → `partial: true`, failed sections listed

### 9.4 Fixtures

- `mock_ga_client` fixture in `conftest.py` (mirrors `mock_runpod_client`)
- Canned GA response JSON under `app/tests/fixtures/ga/` — one file per report type

No live GA calls in CI. Live verification is a manual rollout step.

## 10. Dependencies

Add to `requirements.txt`:
```
google-analytics-data>=0.18.0
cachetools>=5.3.0
```

`google-auth` is already a transitive dependency of other Google libraries (e.g. `google-cloud-storage`), so impersonation support is already installed.

## 11. Rollout plan

1. **Merge & deploy dark** — all code merged, no env vars set, `ga_enabled=False` in prod. Zero user-facing change.
2. **Run `scripts/setup_ga_access.sh`** against `sb-gcp-project-01`. Idempotent.
3. **Manual GA property grants** — add `ga-reader@...` as Viewer on both properties (506611499, 448469065) via GA admin UI.
4. **Verify local impersonation** — developer runs the impersonation commands, starts backend locally, loads `/admin/google-analytics`, confirms data returns.
5. **Set Cloud Run env vars** — `GA_IMPERSONATION_TARGET`, `GA_PROPERTIES`. Redeploy; `ga_enabled` flips true.
6. **Prod smoke test** — admin loads each property and each time range. Check Cloud Run logs for GA errors.
7. **Monitor quota** — GA Data API free tier is generous (~25k tokens/day per project); with 1h caching, 5 reports × 2 properties × 5 ranges, usage is far below the cap. Log-based alert on `RESOURCE_EXHAUSTED`.

## 12. Definition of Done (per `CLAUDE.md`)

- Tests written and `pytest app/tests/ -v` passes
- `make lint-check` passes
- `npm run build` succeeds in `frontend/`
- `npm run lint` passes in `frontend/`
- `npm audit` clean in `frontend/` (no new high/critical)
- Manual smoke test against both properties with real GA creds
- Operator runbook committed at `docs/google-analytics.md`

## 13. Open questions

_None at design-approval time. Any surfaced during planning or implementation should be added here._
