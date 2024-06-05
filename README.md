# Sunbird AI API

![coverage badge](coverage.svg)
![tests](https://github.com/SunbirdAI/sunbird-ai-api/actions/workflows/build-test.yml/badge.svg)

This repository contains code for the publicly accessible Sunbird AI APIs.

To get started using the API, [view the tutorial](tutorial.md).

## Getting started locally for Windows

#### Ensure virtualization is enabled on your computer.

This is required because CPU virtualization is needed for Windows to emulate Linux. For more on enabling [virtualization](https://www.ninjaone.com/blog/enable-hyper-v-on-windows/).

#### Ensure your windows is fully updated.
Install [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) (Windows Subsystem for Linux).
This is required because redis is not officially supported on Windows.

After successfully installing `wsl`:

- Press windows button and in the search bar type `windows features on or off`
- Click on `Turn Windows features on or off` and a pop-up window will appear
- Ensure option `Windows Subsystem for Linux` is checked
- Restart your computer and launch `Ubuntu` and continue with `Getting started locally on Linux`

## Getting started locally on Linux
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
- Install [Redis](https://redis.io/), this is required for the Rate Limiting functionality.
- Start the Redis sever: `sudo service redis-server start` (see docs if you're on Windows without WSL).
- Also make sure the postgres service is running: `sudo service postgresql start`.
- Install [tailwind css](https://tailwindcss.com/docs/installation).
- Run tailwind in a separate terminal tab: `npx tailwindcss -i ./app/static/input.css -o ./app/static/output.css --watch`. This step is only necessary if you're going to make changes to the frontend code.
- Run the app: `uvicorn app.api:app --reload`.

Running the migrations with alembic:
- After making a change to the models, run the command `alembic revision --autogenerate -m 'message'` to make the migrations.
- Check the created migration file in `app/alembic/versions` to ensure it does what's expected.
- Apply the migration with `alembic upgrade head`.

## Deployment
The app is deployed on Google Cloud Run and is backed by PostgreSQL DB hosted in Google Cloud SQL.

## Other docs
- Checkout the [System design document](https://github.com/SunbirdAI/sunbird-docs/blob/main/06-design-docs/language/API_Framework.md) (you need to part of the Sunbird organization to view this).
- Checkout the [Deployment Guide](https://github.com/SunbirdAI/sunbird-ai-api/blob/main/api-deployment-docs.md).
