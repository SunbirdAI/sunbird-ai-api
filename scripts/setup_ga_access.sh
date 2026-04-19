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
