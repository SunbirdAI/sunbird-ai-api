#!/bin/bash

set -e

APP_NAME="sunbirdai-api"

# Log in to Heroku Container Registry
heroku container:login

# Build and Push the Docker Image
docker build -t registry.heroku.com/$APP_NAME/web .
docker push registry.heroku.com/$APP_NAME/web

# Release the Docker Image
heroku container:release web --app $APP_NAME

# Run Alembic Migrations
heroku run alembic upgrade head --app $APP_NAME
