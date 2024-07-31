#!/bin/bash

# Create the firebase_credentials.json file from the environment variable
echo "$GCP_CREDENTIALS" > /app/firebase_credentials.json

# Set the GOOGLE_APPLICATION_CREDENTIALS environment variable
export GOOGLE_APPLICATION_CREDENTIALS=/app/firebase_credentials.json

# Run Alembic migrations
heroku run alembic upgrade head --app $HEROKU_APP_NAME
