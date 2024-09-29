#!/usr/bin/env bash

set -x

# Set your variables
PROJECT_ID="sb-gcp-project-01"
SERVICE_ACCOUNT_NAME="cloud-run-deployer"
SERVICE_ACCOUNT_DISPLAY_NAME="Cloud Run Deployer"
KEY_FILE_PATH="./service-account-key.json"  # Path to save the credentials file

# Enable necessary GCP APIs (if not already enabled)
# gcloud services enable iam.googleapis.com cloudresourcemanager.googleapis.com cloudbuild.googleapis.com run.googleapis.com

# Create a new service account
gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME \
  --project $PROJECT_ID \
  --display-name "$SERVICE_ACCOUNT_DISPLAY_NAME"

# Define the service account email
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Assign roles to the service account
# Cloud Run Admin: deploy services
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member "serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --role "roles/run.admin"

# Cloud Build Service Account: build and push images
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member "serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --role "roles/cloudbuild.builds.editor"

# Storage Admin: manage GCR or Artifact Registry
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member "serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --role "roles/storage.admin"

gcloud iam service-accounts add-iam-policy-binding \
  379507182035-compute@developer.gserviceaccount.com \
  --member="serviceAccount:cloud-run-deployer@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"


# Create and download a JSON key for the service account
gcloud iam service-accounts keys create $KEY_FILE_PATH \
  --iam-account $SERVICE_ACCOUNT_EMAIL

echo "Service account key saved to $KEY_FILE_PATH"
