# Admin Billing Analytics (Runpod + Modal)

Admin-only dashboard at `/admin/billing` reporting infrastructure spend, runtime,
and storage across Runpod and Modal. Backed by `/api/admin/analytics/billing/*`.

## Configuration

Environment variables:

- `RUNPOD_API_KEY` — Runpod billing API auth (already used elsewhere).
- `MODAL_TOKEN_ID` + `MODAL_TOKEN_SECRET` — Modal billing API (Team/Enterprise plan).
- `RUNPOD_BILLING_BASE_URL` — optional, defaults to `https://rest.runpod.io/v1`.
- `BILLING_CACHE_TTL_SECONDS` — optional, defaults to 3600.

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
