# Vast.ai Training Billing + Dashboard Categories — Design Spec

**Date:** 2026-07-01
**Status:** Approved for planning
**Author:** Patrick Walukagga (with Claude Code)

## Summary

Extend the Admin Billing dashboard from a single Runpod+Modal view into **category
sections**, and add **Vast.ai** as a new "Training" category. The `/admin/billing` page
gains a tab switcher:

1. **Inference Billing** (Runpod + Modal) — the existing dashboard.
2. **Training Billing** (Vast.ai) — new.
3. **Cloud infrastructure** (AWS, GCP, Heroku) — reserved for a later, separate spec.

The design introduces a thin **category** abstraction over the existing provider-agnostic
pipeline so additional categories/providers slot in without structural change.

## Decisions (locked)

| Decision | Choice |
|---|---|
| Category abstraction | **Approach A** — thin `PROVIDER_CATEGORY` map + `category` query param; reuse all existing machinery |
| Vast.ai contract modeling | **Amortize** cost/runtime across contract days for charts/summary **+ a per-job (per-contract) table** |
| Training UI | **Reuse the Inference layout** (same components), scoped to Vast.ai with training labels |
| Vast.ai contract types | **instance + volume** (compute + persistent storage) |
| Cloud infra (AWS/GCP/Heroku) | **Deferred** to a later spec; category abstraction designed to accommodate it |

## Scope

### In this spec
- Category abstraction: `PROVIDER_CATEGORY` map + `category` query param on the billing
  endpoints; service resolves `(category, provider)` → provider list.
- `VastaiAnalyticsProvider`: fetch `/api/v0/charges/` (paginated), parse per-contract items,
  amortize into per-day `BillingRecord`s.
- Frontend: tab switcher on `/admin/billing`; Training tab reuses the Inference layout with a
  per-job table and training-appropriate labels; Cloud tab present but disabled.
- Tests: provider (mocked), category routing, endpoint `category` param, frontend build.

### Deferred (later specs)
- Cloud infrastructure billing (AWS Cost Explorer, GCP Billing, Heroku) as a third category.
- AI assistant / forecasting (already deferred from the inference spec).

## Architecture

### Category abstraction (Approach A)
- `PROVIDER_CATEGORY = {"runpod": "inference", "modal": "inference", "vastai": "training"}`.
  Helper `providers_in_category(category) -> list[str]`. Lives in a small module
  (`app/integrations/billing/categories.py`) or as a constant in the service module.
- Endpoints gain `category` (`inference` | `training`; default `inference`). `provider`
  continues to filter within a category (`all` = all providers in the category).
- `BillingAnalyticsService._providers_for(category, provider)` returns the concrete provider
  instances. The record schema, aggregation, caching, coalescing, and quantization are
  unchanged. Amortization lives entirely inside the Vast.ai provider, so the aggregation layer
  stays provider-agnostic.

### Backend layout
```
app/integrations/billing/
    categories.py   # PROVIDER_CATEGORY + providers_in_category()   (new)
    vastai.py       # VastaiAnalyticsProvider (async httpx, paginated, amortizing)  (new)
app/services/billing_analytics/service.py   # category-aware _providers_for; register vastai
app/schemas/billing_analytics.py            # Provider Literal += "vastai"
app/routers/admin_billing.py                # + category query param on all endpoints
app/core/config.py                          # + Vast.ai settings
frontend/src/pages/AdminBilling.tsx         # + category tab switcher; training labels
frontend/src/hooks/useBillingAnalytics.ts   # + category in requests
```

## Vast.ai provider + amortization

### Fetch
- `GET {VAST_BILLING_BASE_URL}/api/v0/charges/` with query params:
  - `select_filters` = JSON string `{"day":{"gte":<unix>,"lte":<unix>},"type":{"in":[...types...]}}`
    (unix **seconds** UTC; types from `VAST_CONTRACT_TYPES`, default `instance,volume`).
  - `limit=500`, cursor pagination via `after_token` ← previous response's `next_token`
    (`/api/v1/billing/charges` returns `pagination.next_page_token`); stop when the token is
    null. Accept both `results[]` and `rows[]` container keys defensively.
  - Auth: `Authorization: Bearer {VAST_API_KEY}`. Handle 429 (rate limit) as
    `ProviderUnavailable` (fail fast; the service already degrades gracefully with a warning).

### Normalize + amortize
For each contract result:
- Parse `items[]` by `type`: `gpu` (extract hours from the description or item amount →
  runtime), `disk`, `bwd`, `bwu` (bandwidth) → a `resource_breakdown` of amounts. Code the
  hours parse defensively (regex on `"96.000 hours at $0.389/hour"`), falling back to `None`
  runtime when unparseable.
- Compute `num_days = max(days_between(start, end), 1)` from the contract's unix `start`/`end`.
- Emit **one `BillingRecord` per contract per day** across `[start, end]`:
  - `provider = "vastai"`
  - `object_id = source` (e.g. `instance-12345678`)
  - `object_name = metadata.label or description`
  - `timestamp = day` (naive UTC, start of day) — the schema's validator keeps it naive UTC
  - `cost = amount / num_days`
  - `runtime_ms = total_gpu_ms / num_days` (or `None`)
  - `storage_gb = None` (Vast.ai reports storage as cost, not GB — documented limitation)
  - `resource_breakdown = {gpu, disk, bwd, bwu}` amounts (also divided per day)
  - `metadata = {kind: "vastai_contract", contract_type, contract_start, contract_end,
    gpu_name, num_days}`
- Amortizing per-day records makes `summary` and `timeseries` smooth and totals correct
  (sum over days = contract total) using the existing aggregation unchanged.

### Per-job table
The Training table is per-contract: group the amortized records by `object_id` (contract) and
sum → job rows (label, GPU, total hours, duration from `contract_start`/`contract_end`, total
cost, contract type). Implemented by adding a generic **`object`** group key to
`aggregation` (maps to `object_name` for any provider, unlike the provider-specific
`endpoint`/`app` keys) and reusing the existing `group_records`/breakdown path — no separate
fetch. `object` is added to `SUPPORTED_GROUP_BYS`. `count` is not shown as "record count" for training
(it would be day-count); the row instead surfaces contract metadata.

## API changes

- All six billing endpoints (`/summary`, `/timeseries`, `/providers`, `/breakdown`, `/table`,
  `/export`) accept a `category` query param (`inference` | `training`, default `inference`),
  validated against the known categories. `provider` filters within the category.
- Summary metrics adapt per category: Inference shows **active endpoints / Modal apps**;
  Training shows **active instances/jobs** (distinct Vast.ai contract `object_id`s). The
  summary computation derives these from the records in scope.
- No new endpoints; `POST /ai` remains reserved (501).

## Frontend (reuse layout)

- Tab switcher at the top of `/admin/billing`:
  **Inference (Runpod & Modal)** | **Training (Vast.ai)** | **Cloud (coming soon — disabled)**.
- Inference tab = current view (`category=inference`, provider filter `all|runpod|modal`).
- Training tab = the same components (cards, cost-over-time line, records table, explainer)
  with `category=training`, training-appropriate labels (e.g. "Active Jobs", "GPU Hours"), and
  the per-job table (grouped by contract).
- The explainer panel gains a Vast.ai section: per-contract billing, amortization across days,
  GPU-hours, storage-as-cost.
- `useBillingAnalytics` threads `category` into every request; the tab controls it.

## Schema / config / caching / testing

- **Schema:** `BillingRecord.provider` Literal += `"vastai"`. No other schema change required
  (amortized records fit the existing model; `metadata` carries contract detail).
- **Config (`config.py`):** `VAST_API_KEY`; `VAST_BILLING_BASE_URL`
  (default `https://console.vast.ai`); `VAST_CONTRACT_TYPES` (default `instance,volume`);
  `VAST_BILLING_TIMEOUT_SECONDS` (default 30). Provider keys server-side only.
- **Caching:** cache key includes the provider set already; add `category` to the key so
  inference and training don't collide. Coalescing/quantization unchanged.
- **Testing:** `test_vastai_billing.py` (mocked httpx: pagination across pages, item/hours
  parsing, amortization math, graceful failure, `is_available` without key); service tests for
  category routing (`category=training` → only vastai; `inference` → runpod+modal); router test
  for the `category` param and validation; frontend build (`tsc && vite build`). Follows
  `asyncio_mode=auto`; reuses existing fixtures. Lint gate: changed files clean under
  black/isort/flake8 (repo `make lint-check`/`npm run lint` are pre-existingly broken).

## Risks

- **Response-shape variance** — reference OpenAPI uses `results[]` + nested `items[]`; Context7
  also shows a `rows[]` + flat-fields variant. Code defensively for both container keys and
  field names; verify against the live API at implementation.
- **Amortization is an approximation** — spreads a contract's cost evenly across its days,
  ignoring intra-contract daily variation. Totals are exact; per-day shape is smoothed.
- **Storage in GB unavailable** for Vast.ai (billed as cost). Training storage is shown as cost
  / GPU-hours rather than GB; the "Avg Storage (GB)" card is inference-oriented and may read 0
  for training (label it accordingly or hide on the Training tab).
- **Pagination + rate limits** — page fully via cursor; treat 429 as `ProviderUnavailable`.

## Future extensibility

- **Cloud infrastructure** (AWS/GCP/Heroku) = a third category: add providers, extend
  `PROVIDER_CATEGORY`, enable the Cloud tab. No structural change to schema/aggregation/UI.
- New providers in any category implement `AnalyticsProvider.fetch_records` only.
