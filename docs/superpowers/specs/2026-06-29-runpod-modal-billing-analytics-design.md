# Admin Billing Analytics (Runpod + Modal) — Design Spec

**Date:** 2026-06-29
**Status:** Approved for planning
**Author:** Patrick Walukagga (with Claude Code)

## Summary

Add an **Admin Billing Analytics** surface that reports infrastructure **spend, runtime,
and storage** across the **Runpod** and **Modal** inference platforms. Data is fetched live
from each provider's billing API, normalized into a single provider-agnostic schema, cached,
aggregated, and served to a new admin dashboard page. The design is provider-agnostic so
additional providers (AWS, GCP, OpenAI, TogetherAI, …) can be added later by implementing a
single interface.

This is a **sibling** of the existing admin analytics surface (`/api/admin/analytics`,
`AdminAnalytics.tsx`), which reports **API request usage** (volume/latency per org). The new
surface reports **infrastructure billing/cost** and lives on its own route.

## Decisions (locked)

| Decision | Choice |
|---|---|
| Scope | **MVP first**, remaining features in clearly-scoped later phases |
| Data source | **Live fetch + cache** (no new DB tables/migrations for MVP) |
| Providers | **Both** Runpod and Modal in the MVP (credentials available) |
| Frontend placement | **New dedicated page/route** (`/admin/billing`) |
| Backend structure | **Approach A** — follow existing repo conventions (integrations/services/schemas/routers + DI in `deps.py`) |

## Scope

### In the MVP
- Provider-agnostic backend: `AnalyticsProvider` interface + `RunpodAnalyticsProvider` +
  `ModalAnalyticsProvider` (live fetch + cache).
- Unified billing schema + reusable, pure aggregation utilities.
- Admin REST endpoints: `summary`, `timeseries`, `providers`, `breakdown`, `table`,
  `export` (CSV).
- New admin frontend page `/admin/billing` reusing existing chart/metric/filter components.
- Filtering: date range, platform, resolution, grouping, search. Sortable/paginated table.
  Core charts (line/bar/pie/stacked).
- Tests: providers mocked, aggregation units, API auth + happy-path, partial-failure,
  frontend smoke.

### Deferred to later phases (designed-for, not built)
- AI Analytics Assistant (`POST .../ai`) + automatic insights/anomalies. The route is
  reserved and returns `501` until implemented. The AI data pipeline consumes the same
  aggregation outputs (structured summary → GPT), never raw billing rows. The exact model
  (brief names `gpt-5.4-mini`; existing client default is `gpt-4o-mini`) is decided at the
  start of that phase via the existing `OpenAIClient`.
- Forecasting / predictions; moving averages beyond basic trend.
- Heatmaps; GPU-utilization charts; Excel/PDF export (CSV is built; JSON export is a trivial
  add when needed).

## Architecture

### Request flow
`AdminBilling.tsx` → `useBillingAnalytics` (axios) → `app/routers/admin_billing.py`
(`CurrentAdminDep`) → `BillingAnalyticsService` → `AnalyticsProvider` implementations →
provider billing APIs. Normalized records are cached (`CacheBackend`); aggregation functions
shape each endpoint's response.

### Backend module layout (Approach A)
```
app/integrations/billing/
    base.py        # AnalyticsProvider ABC + ProviderUnavailable error + ProviderQuery
    runpod.py      # RunpodAnalyticsProvider (async httpx)
    modal.py       # ModalAnalyticsProvider (Modal SDK)
app/services/billing_analytics/
    service.py     # BillingAnalyticsService orchestrator + get_billing_analytics_service()
    aggregation.py # pure functions over list[BillingRecord]
app/schemas/billing_analytics.py    # unified schema + request/response envelopes
app/routers/admin_billing.py         # APIRouter, prefix /api/admin/analytics/billing
app/deps.py        # + BillingAnalyticsServiceDep
app/api.py         # mount router
app/core/config.py # + Modal token + cache TTL + optional Runpod base URL
```

Rationale: honors the brief's abstraction goals (provider-agnostic interface, isolated
providers, reusable aggregation) while staying native to the codebase. Reuses `CacheBackend`,
`OpenAIClient`, `CurrentAdminDep`, and the singleton + `Annotated` DI idiom.

## Unified analytics schema

A single normalized bucket-row both providers map into:

```python
class BillingRecord(BaseModel):
    provider: Literal["runpod", "modal"]
    object_id: str                    # Runpod endpointId / Modal object_id
    object_name: str                  # human label (endpoint id or App description)
    timestamp: datetime               # UTC, start of bucket
    cost: float                       # USD
    runtime_ms: int | None            # Runpod timeBilledMs; None for Modal
    storage_gb: float | None          # Runpod diskSpaceBilledGB; None for Modal
    gpu: str | None                   # when grouped by GPU (Runpod)
    environment: str | None           # Modal environment_name
    tags: dict[str, str] = {}         # Modal tags
    resource_breakdown: dict[str, float] = {}  # Modal cost_by_resource (best-effort)
    metadata: dict = {}
```

Response envelopes (all provider-independent, Chart.js-friendly like existing endpoints):
- `SummaryResponse` — executive cards.
- `TimeseriesResponse` — `labels` + per-series datasets.
- `ProvidersResponse` — per-platform comparison.
- `BreakdownResponse` — grouped aggregates.
- `TableResponse` — paginated rows + total count.
- All responses may include a `warnings: list[str]` field for partial-data conditions.

## Provider layer + normalization

### Interface
`AnalyticsProvider` (ABC), async:
- `name: str`
- `is_available() -> bool`
- `fetch_records(query: ProviderQuery) -> list[BillingRecord]` — the single primitive.

`summary/timeseries/breakdown` are **not** provider methods; they are computed by the
aggregation layer from records, keeping providers thin and aggregation provider-agnostic.

`ProviderQuery` carries: `start`, `end`, `base_resolution` (`hour`|`day`), optional
`grouping`, `endpoint_ids`, `gpu_types`, `data_center_ids`, `tag_names`.

### RunpodAnalyticsProvider
- Lazy `httpx.AsyncClient` with timeout + retry wrapper (mirrors
  `app/integrations/orpheus_modal.py`).
- `GET https://rest.runpod.io/v1/billing/endpoints` with `bucketSize`, `startTime`,
  `endTime`, optional `grouping` (`endpointId`|`gpuTypeId`), `dataCenterId[]`, `gpuTypeId[]`,
  `endpointId`. **Omitting `endpointId` returns billing across all endpoints.**
- Auth: `Authorization: Bearer {RUNPOD_API_KEY}`.
- Normalize live response rows (per real sample):
  `amount→cost`, `timeBilledMs→runtime_ms`, `diskSpaceBilledGB→storage_gb`,
  `endpointId→object_id/object_name`, `time→timestamp` (UTC). `gpuTypeId→gpu` when grouped by
  GPU. **Code defensively** — the documented response shape (Context7) differs slightly from
  the live sample; verify against the live API at implementation.

### ModalAnalyticsProvider
- Wraps `modal.billing.workspace_billing_report(start, end, resolution, tag_names=["*"])`
  (GA since modal-client v1.3.3, 2026-02-12; requires Team/Enterprise plan).
- Auth via the Modal SDK's standard token pair, read from env: `MODAL_TOKEN_ID` +
  `MODAL_TOKEN_SECRET` (passed to a `modal.Client` and threaded into the billing call).
- Normalize: `object_id`, `description→object_name`, `cost (Decimal→float)`,
  `interval_start→timestamp` (UTC), `environment_name→environment`, `tags`,
  `cost_by_resource→resource_breakdown` (best-effort; `runtime_ms`/`storage_gb` are `None`).
- **Constraint:** Modal resolution is only `"d"` or `"h"`. Leave a small buffer after the end
  of the query interval to allow for collection delay.

### Resolution strategy
Providers fetch at a **base resolution** (`hour` or `day`). The aggregation layer rolls up to
`week`/`month`/`year` **uniformly** for both providers (required because Modal lacks native
week/month/year). Single rollup code path → consistent buckets across providers.

### Concurrency + partial failure
The orchestrator fans out to the selected providers concurrently (`asyncio.gather`). If one
provider raises `ProviderUnavailable`, results from the other are still returned, and a
`warnings[]` entry notes the degraded provider.

## Service, aggregation & caching

### aggregation.py (pure, unit-testable)
Functions over `list[BillingRecord]`: `sum_cost`, `average_cost`, `runtime_totals`,
`storage_totals`, `group_by(field)`, `rollup_timeseries(records, resolution)`,
`trend`/`cost_growth`, `comparison`, `top_n(field)`. Reused by every endpoint and (later) the
AI pipeline.

### BillingAnalyticsService (singleton orchestrator)
1. Build `ProviderQuery` from request filters; resolve `provider` (`all`|`runpod`|`modal`).
2. Fetch normalized records concurrently from the selected providers.
3. Cache raw normalized records in `CacheBackend`, keyed by
   `(providers, start, end, base_resolution, filters)`, TTL `BILLING_CACHE_TTL_SECONDS`
   (default 3600). Identical requests skip provider calls.
4. Run aggregation functions to build each endpoint's response envelope.

`get_billing_analytics_service()` singleton factory; registered in `deps.py` as
`BillingAnalyticsServiceDep`.

## API endpoints (MVP)

All under `/api/admin/analytics/billing`, gated by `CurrentAdminDep`. Unified `provider`
query param (`all`|`runpod`|`modal`). Custom exception classes from
`app/core/exceptions.py`.

| Method / Path | Purpose |
|---|---|
| `GET /summary` | Total + average spend, runtime, storage; active endpoints/apps; highest-cost endpoint & platform |
| `GET /timeseries` | Cost/runtime/storage over time; honors `resolution`, `groupBy` |
| `GET /providers` | Per-platform comparison (spend / runtime share) |
| `GET /breakdown` | Grouped aggregates: endpoint, gpu, datacenter, app, environment, tags |
| `GET /table` | Paginated, sortable normalized rows; honors `search` |
| `GET /export` | CSV of the current filter set (JSON-ready for later) |
| `POST /ai` | **Deferred** — reserved route; returns `501` until the AI phase |

Shared query params: `provider`, `startTime`/`endTime` (plus named ranges:
`today`, `yesterday`, `last_7_days`, `last_30_days`, `last_90_days`, `this_month`,
`last_month`, `custom`), `resolution` (`hour`|`day`|`week`|`month`|`year`), `groupBy`,
`search`, `page`/`pageSize`, `sort`.

## Frontend (new page)

- **Route:** `/admin/billing` in `App.tsx` behind `RequireAuth` + admin check; add to admin
  nav next to "Admin Analytics". `DashboardRedirect` unchanged.
- **Page:** `pages/AdminBilling.tsx` reusing `MetricCard`, `ChartCard`, `MultiSelect`, plus a
  billing-specific `FilterBar` (platform / date-range / resolution / grouping / search).
- **Hook:** `hooks/useBillingAnalytics.ts` mirroring the `useAdminAnalytics` trio (data,
  filters, export) calling the six endpoints via `axios`.
- **Charts (Chart.js, already installed):** line (cost/runtime over time), bar (cost by
  endpoint/GPU/app), pie (spend per platform/GPU), stacked (provider comparison). Executive
  summary cards row. Sortable/paginated table with CSV export button.
- Dark-mode + skeleton-loading patterns copied from `AdminAnalytics.tsx`.

## Config / env additions (`app/core/config.py`)

- `MODAL_TOKEN_ID` + `MODAL_TOKEN_SECRET` — Modal billing auth (SDK standard token pair).
- `BILLING_CACHE_TTL_SECONDS` (default 3600).
- `RUNPOD_BILLING_BASE_URL` (optional; default `https://rest.runpod.io/v1`).
- `RUNPOD_API_KEY` already read via env. Provider keys are never returned to the client.

## Error handling

- Per-provider `try/except` → `ProviderUnavailable`; orchestrator returns partial data plus a
  `warnings[]` field. Retries on transient `httpx` errors / 5xx (existing retry idiom).
- Empty reports return empty envelopes, not errors. Bounded timeouts. Authentication failures
  surface as a clear admin-facing error without leaking provider details.

## Security

- All endpoints admin-only (`CurrentAdminDep`). Provider API keys server-side only.
- Analytics requests logged via existing logging/monitoring.
- AI prompt sanitization reserved for the AI phase (assistant always grounded in real
  aggregation outputs, never hallucinated).

## Testing

- `app/tests/test_admin_billing.py` — auth (401 unauthenticated, 403 non-admin), endpoint
  happy-paths with **mocked providers**, partial-failure (one provider down → `warnings`).
- `app/tests/test_billing_aggregation.py` — pure-function units (sum/avg/group_by/rollup/
  trend/comparison/top_n).
- Provider tests with mocked `httpx` (Runpod) and mocked Modal SDK call.
- Frontend smoke test: page renders with mocked axios.
- Follows `asyncio_mode=auto`; reuses `admin_client`, `async_client`, `authenticated_client`
  fixtures. `make lint-check` clean.

## Implementation roadmap (small, reviewable commits)

1. Schema (`billing_analytics.py`) + aggregation pure functions (+ unit tests).
2. `AnalyticsProvider` base + Runpod provider (+ mocked tests).
3. Modal provider (+ mocked tests).
4. `BillingAnalyticsService` + caching + DI registration.
5. Router endpoints (summary/timeseries/providers/breakdown/table/export) + API tests.
6. Config / env additions.
7. Frontend page + hook + route + nav + charts (+ smoke test, `npm run build`, `npm run lint`).
8. Docs + roadmap notes for deferred AI/forecasting phases.

## Risks

- **Runpod response-shape drift** (documented vs. live sample) — code defensively; verify
  against the live API; normalize tolerantly.
- **Modal billing collection delay / partial intervals** — add an end-of-interval buffer;
  surface as informational, not an error.
- **Modal resolution limited to d/h** — handled by the uniform rollup layer.
- **Provider latency** — concurrent fetch + caching; bounded timeouts.
- **Plan gating (Modal Team/Enterprise)** — `is_available()` + `ProviderUnavailable` degrade
  gracefully if access lapses.

## Future extensibility

- New providers = a new `AnalyticsProvider` subclass only; aggregation/endpoints unchanged.
- AI assistant consumes the same aggregation outputs (structured summary → GPT).
- A persistence layer (DB tables + scheduled sync) can slot behind `BillingAnalyticsService`
  without changing the API contract, if longer history or faster queries are needed later.

## Implementation status

MVP implemented per `docs/superpowers/plans/2026-06-29-admin-billing-analytics.md`.
Deferred items (AI assistant, forecasting, datacenter/tags grouping, heatmaps,
Excel/PDF export, DB persistence) remain for later phases.
