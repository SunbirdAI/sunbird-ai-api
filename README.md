# Sunbird AI API
This repository contains code for the publicly accessible Sunbird AI APIs.

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

- Run the app: `uvicorn api:app --reload`

Running the migrations with alembic:
- After making a change to the models, run the command `alembic revision --autogenerate -m 'message'` to make the migrations.
- Check the created migration file in `app/alembic/versions` to ensure it does what's expected.
- Apply the migration with `alembic upgrade head`.
