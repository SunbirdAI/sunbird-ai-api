#!/bin/bash

# Run Alembic migrations
alembic upgrade head

# Start the FastAPI application with Uvicorn (2 workers for Azure)
uvicorn app.api:app --host 0.0.0.0 --port ${PORT} --workers 2
