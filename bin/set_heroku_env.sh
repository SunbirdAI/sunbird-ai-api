#!/bin/bash

set -e

# Ensure a Heroku app name is provided
if [ -z "$1" ]; then
  echo "Usage: $0 <heroku-app-name>"
  exit 1
fi

HEROKU_APP_NAME=$1

# Load environment variables from .env.prod
if [ ! -f .env.prod ]; then
  echo ".env.prod file not found!"
  exit 1
fi

# Read .env.prod file and set Heroku config variables
while IFS= read -r line || [[ -n "$line" ]]; do
  # Ignore empty lines and comments
  if [[ -z "$line" || "$line" == \#* ]]; then
    continue
  fi

  # Split the line into variable name and value
  IFS='=' read -r varname value <<< "$line"

  # Strip trailing spaces from variable name and value
  varname=$(echo "$varname" | xargs)
  value=$(echo "$value" | xargs)

  # Set the Heroku config variable
  heroku config:set "$varname=$value" --app "$HEROKU_APP_NAME"
done < .env.prod

# Set the Google credentials from the base64-encoded file
ENCODED_CREDENTIALS=$(cat firebase-credentials.json.b64)
heroku config:set GOOGLE_CREDENTIALS_JSON_B64="$ENCODED_CREDENTIALS" --app "$HEROKU_APP_NAME"

echo "Environment variables set for Heroku app: $HEROKU_APP_NAME"
