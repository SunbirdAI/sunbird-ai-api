#!/usr/bin/env bash
set -euo pipefail

#----------------------------------------------------------------------
# Script to create Workload Identity Federation for GitHub Actions
#----------------------------------------------------------------------

# Required environment variables:
#   GCP_PROJECT_ID            Your GCP project ID
#   GITHUB_REPOSITORY        GitHub repo in the form org/repo
#   WIF_POOL_ID               Desired Workload Identity Pool ID (e.g. github-pool)
#   WIF_PROVIDER_ID           Desired Provider ID (e.g. github-provider)
#   SA_NAME                   Service account name (e.g. github-actions-deployer)
#----------------------------------------------------------------------
export GCP_PROJECT_ID=sb-gcp-project-01
export GITHUB_REPOSITORY=SunbirdAI/sunbird-ai-api
export WIF_POOL_ID=github-actions-pool
export WIF_PROVIDER_ID=github-provider
export SA_NAME=gha-cloud-run-deploy

: "${GCP_PROJECT_ID:?Need to set GCP_PROJECT_ID}"  
: "${GITHUB_REPOSITORY:?Need to set GITHUB_REPOSITORY}"  
: "${WIF_POOL_ID:?Need to set WIF_POOL_ID}"       
: "${WIF_PROVIDER_ID:?Need to set WIF_PROVIDER_ID}"  
: "${SA_NAME:?Need to set SA_NAME}"              

# Ensure gcloud uses the correct project
echo "> Setting gcloud project to $GCP_PROJECT_ID..."
gcloud config set project "$GCP_PROJECT_ID"

# Enable required APIs
echo "> Enabling required GCP APIs..."
gcloud services enable iamcredentials.googleapis.com \
                             iam.googleapis.com \
                             sts.googleapis.com

# Create Workload Identity Pool (safe create)
echo "> Creating Workload Identity Pool: $WIF_POOL_ID ..."
if ! gcloud iam workload-identity-pools describe "$WIF_POOL_ID" --location="global" --format="value(name)" &>/dev/null; then
  gcloud iam workload-identity-pools create "$WIF_POOL_ID" \
    --location="global" \
    --display-name="GitHub Actions Pool"
fi

# Get full pool resource name
echo "> Retrieving pool resource name..."
POOL_NAME=$(gcloud iam workload-identity-pools describe "$WIF_POOL_ID" \
  --location="global" --format="value(name)")

echo "> Pool resource: $POOL_NAME"

# Wait for pool to be fully available before creating provider
sleep 10

# Create OIDC provider (safe create)
echo "> Creating OIDC provider: $WIF_PROVIDER_ID ..."
if ! gcloud iam workload-identity-pools providers describe "$WIF_PROVIDER_ID" \
     --workload-identity-pool="$WIF_POOL_ID" --location="global" &>/dev/null; then
  gcloud iam workload-identity-pools providers create-oidc "$WIF_PROVIDER_ID" \
    --workload-identity-pool="$WIF_POOL_ID" \
    --location="global" \
    --display-name="GitHub OIDC Provider" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --allowed-audiences="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition="attribute.repository=='$GITHUB_REPOSITORY' && attribute.ref=='refs/heads/main'"
fi

# Restrict to specific repository and branch (main)
echo "> Restricting provider to repo $GITHUB_REPOSITORY on main branch"
gcloud iam workload-identity-pools providers update-oidc "$WIF_PROVIDER_ID" \
  --workload-identity-pool="$WIF_POOL_ID" \
  --location="global" \
  --allowed-audiences="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="attribute.repository=='$GITHUB_REPOSITORY' && attribute.ref=='refs/heads/main'"

# Create Service Account (safe create)
echo "> Creating service account: $SA_NAME ..."
if ! gcloud iam service-accounts describe "${SA_NAME}@${GCP_PROJECT_ID}.iam.gserviceaccount.com" &>/dev/null; then
  gcloud iam service-accounts create "$SA_NAME" \
    --display-name="GitHub Actions Deployer"
fi
SA_EMAIL="${SA_NAME}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"

echo "> Service Account Email: $SA_EMAIL"

# Grant roles to Service Account
echo "> Granting roles to $SA_EMAIL"
gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
  --member="serviceAccount:$SA_EMAIL" --role="roles/run.admin" || true

gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
  --member="serviceAccount:$SA_EMAIL" --role="roles/iam.serviceAccountUser" || true

# Bind Workload Identity Pool to Service Account
echo "> Binding WIF pool to service account"
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/${POOL_NAME}/attribute.repository/${GITHUB_REPOSITORY}"

# Output provider resource
PROVIDER_RESOURCE="${POOL_NAME}/providers/${WIF_PROVIDER_ID}"
echo -e "\nDone! Add these to GitHub Secrets:\n  WORKLOAD_IDENTITY_PROVIDER=${PROVIDER_RESOURCE}\n  GCP_SA_EMAIL=$SA_EMAIL"
