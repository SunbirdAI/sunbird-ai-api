# Sunbird AI API

![coverage badge](coverage.svg)
![tests](https://github.com/SunbirdAI/sunbird-ai-api/actions/workflows/build-test.yml/badge.svg)

This repository contains code for the publicly accessible Sunbird AI APIs.

To get started using the API, [view the tutorial](tutorial.md).

## Getting started locally
To run the app locally:
- Create and activate a local environment
- Install the requirements: `pip install -r requirements.txt`.
- Set the environment variables in a `.env` file, the following variables are required:
```
ENDPOINT_ID
PROJECT_ID
SECRET_KEY
DATABASE_URL
```

- Run the app: `uvicorn app.api:app --reload`

Running the migrations with alembic:
- After making a change to the models, run the command `alembic revision --autogenerate -m 'message'` to make the migrations.
- Check the created migration file in `app/alembic/versions` to ensure it does what's expected.
- Apply the migration with `alembic upgrade head`.

## Deployment
The app is deployed on Google Cloud Run and is backed by PostgreSQL DB hosted in Google Cloud SQL.
