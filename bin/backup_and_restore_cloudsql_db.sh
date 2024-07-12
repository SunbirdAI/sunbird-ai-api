#!/bin/bash

# Ensure the script exits if any command fails
set -e

# ENV VARIABLES
PROJECT_ID="sb-gcp-project-01"
INSTANCE_ID="sunbird-api-db"
DB_NAME="sunbirdapidb"
LOCAL_PATH="cloudsql_db_backups"
PROJECT_REGION="europe-west1"
PROJECT_ZONE="europe-west1-a"
BUCKET_NAME="sb-api-db-backups-$PROJECT_ID"

echo "CHECKING THE ACTIVE CONFIG BEFORE MAKING ANY CHANGE..."
gcloud config set project $PROJECT_ID
HEROKU_DB_URL=$(heroku config:get DATABASE_URL -a sunbirdai-api)

# Generate a timestamp
TIMESTAMP=$(date +%Y%m%d%H%M%S)

# Create the export file name with timestamp
EXPORT_FILE_NAME="${DB_NAME}-backup-${TIMESTAMP}.sql"

# Set the project ID
gcloud config set project $PROJECT_ID

# Construct the Cloud SQL service account email
CLOUD_SQL_SERVICE_ACCOUNT="p379507182035-6gswj4@gcp-sa-cloud-sql.iam.gserviceaccount.com"

# Grant the service account permissions on the bucket
gsutil iam ch serviceAccount:$CLOUD_SQL_SERVICE_ACCOUNT:roles/storage.objectAdmin gs://$BUCKET_NAME

# Export the database to the GCS bucket
gcloud sql export sql $INSTANCE_ID gs://$BUCKET_NAME/$EXPORT_FILE_NAME --database=$DB_NAME

# Download the exported file from the GCS bucket
gsutil cp gs://$BUCKET_NAME/$EXPORT_FILE_NAME $LOCAL_PATH

# Restore the database to Heroku PostgreSQL
psql $HEROKU_DB_URL -a sunbirdai-api < $LOCAL_PATH/$EXPORT_FILE_NAME

echo "Backup from Cloud SQL and restore to Heroku PostgreSQL completed successfully."
