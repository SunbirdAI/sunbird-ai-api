# Admin Billing Analytics (Runpod + Modal)

Admin-only dashboard at `/admin/billing` reporting infrastructure spend, runtime,
and storage across Runpod and Modal. Backed by `/api/admin/analytics/billing/*`.

## Configuration

Environment variables:

- `RUNPOD_API_KEY` — Runpod billing API auth (already used elsewhere).
- `MODAL_TOKEN_ID` + `MODAL_TOKEN_SECRET` — Modal billing API (Team/Enterprise plan).
- `RUNPOD_BILLING_BASE_URL` — optional, defaults to `https://rest.runpod.io/v1`.
- `RUNPOD_BILLING_ENDPOINT_IDS` — optional, comma-separated Runpod endpoint IDs to
  scope billing to (default `f4qvczc8rce33x,yapuzewu3ebmzq`; empty = all endpoints).
  Runpod's `endpointId` filter is single-valued, so scoping is applied by fetching
  all endpoints and filtering the normalized records to this set.
- `RUNPOD_INCLUDE_NETWORK_VOLUMES` — optional bool, default `true`. Adds account-level
  Runpod network volume storage costs (`/billing/networkvolumes`) to the totals as a
  "Network Volumes" line (not counted as an endpoint).
- `BILLING_CACHE_TTL_SECONDS` — optional, defaults to 3600.
- `BILLING_CACHE_QUANTUM_SECONDS` — optional, defaults to 60. Quantizes `now` for
  named date ranges so repeated/concurrent identical requests share a cache key and
  return consistent results within the window.

## Field meanings

- **cost** — USD billed by the provider for the bucket. Modal amounts are pre-credit.
- **runtime_ms** — Runpod `timeBilledMs` (billed worker-time). Modal reports none.
- **storage_gb** — Runpod `diskSpaceBilledGb` / `diskSpaceBilledGB`. This is **GB-hours**
  (capacity × hours billed), not a GB snapshot: a steady 350 GB volume reports
  350 × 24 = 8,400 per day. Reconciles to cost (e.g. network volumes: 350 GB ×
  $0.07/GB-month ÷ 30 ≈ $0.8166/day). The summary's `avg_storage_gb` divides total
  GB-hours by the hours in the range to give the time-weighted average provisioned GB;
  the table/CSV show the raw per-bucket GB-hours.
- **active_endpoints** — distinct Runpod endpoints (network volumes excluded).
- **Network Volumes** — account-level Runpod storage; included in spend/storage totals,
  not counted as an endpoint.

## Endpoints

All admin-only (`CurrentAdminDep`), under `/api/admin/analytics/billing`:

| Endpoint | Purpose |
|---|---|
| `GET /summary` | Executive summary cards |
| `GET /timeseries` | Cost/runtime/storage over time (`resolution`, `group_by`) |
| `GET /providers` | Per-platform comparison |
| `GET /breakdown` | Grouped aggregates (`group_by`) |
| `GET /table` | Paginated, sortable, searchable rows |
| `GET /export` | CSV export |
| `POST /ai` | Reserved (501) — AI assistant phase |

Shared query params: `provider` (all/runpod/modal), `range` (named) or
`start`/`end` (ISO), `resolution` (hour/day/week/month/year). `group_by`
supports: provider, endpoint, app, gpu, environment.

## Architecture

`router → BillingAnalyticsService → AnalyticsProvider (Runpod|Modal) → cache → aggregation`.
Providers fetch at a base resolution (hour/day); the aggregation layer rolls up to
week/month/year. Records are cached in `CacheBackend` keyed by query.

## Deferred (later phases)

- AI Analytics Assistant (`POST /ai`) + automatic insights/anomalies — consume the
  same aggregation outputs (structured summary → GPT), never raw rows.
- Forecasting / predictions.
- `group_by` for datacenter and tags; GPU-utilization charts; heatmaps; Excel/PDF export.
- Optional DB persistence + scheduled sync for longer history (slots behind the
  service without changing the API contract).
