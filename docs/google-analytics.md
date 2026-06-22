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

Do **not** set `gcloud config set auth/impersonate_service_account`. The
backend impersonates `ga-reader` at the Python layer (via
`google.auth.impersonated_credentials` in
`app/integrations/google_analytics.py`); gcloud-level impersonation is
not needed and will break IAM-modifying commands.

```bash
gcloud auth application-default login
# If you previously set gcloud-level impersonation, unset it:
gcloud config unset auth/impersonate_service_account
cp .env.example .env  # ensure GA_IMPERSONATION_TARGET + GA_PROPERTIES are set
uvicorn app.api:app --reload
```

You (and any teammate who needs local access) must have
`roles/iam.serviceAccountTokenCreator` on `ga-reader`. Grant it with:

```bash
./scripts/setup_ga_access.sh you@sunbird.ai
```

## Debugging

- **`PERMISSION_DENIED: iam.serviceAccounts.getAccessToken` from the app**
  — your user (`gcloud auth list`) lacks `tokenCreator` on `ga-reader`.
  Run `./scripts/setup_ga_access.sh your@sunbird.ai`, then restart
  uvicorn (the impersonated-credentials object is built once at startup).
- **`PERMISSION_DENIED: iam.serviceAccounts.getIamPolicy` when running
  setup or granting IAM** — you have gcloud-level impersonation active,
  so commands run as `ga-reader` instead of you. Fix with
  `gcloud config unset auth/impersonate_service_account`, then retry.
- **403 / permission denied from GA** — the `ga-reader` SA is missing
  Viewer access on the property; re-check Property Access Management.
- **429 / quota** — either the GA Data API quota was exceeded (rare) or
  multiple Cloud Run instances missed the cache simultaneously. Raise
  `GA_CACHE_TTL_SECONDS` or switch to a shared cache (Upstash).
- **"Google Analytics is not configured" (503)** — env vars missing in
  Cloud Run.
- **Empty data for new property** — GA ingestion lags 4–24h; verify by
  looking at the same range in the GA web UI.
