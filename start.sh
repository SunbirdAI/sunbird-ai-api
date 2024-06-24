#!/bin/bash

# Run Alembic migrations
alembic upgrade head

# Start the FastAPI application with Uvicorn
uvicorn app.api:app --host 0.0.0.0 --port ${PORT} --workers 1
