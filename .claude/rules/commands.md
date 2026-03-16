# Development Commands

## Running the App

```bash
uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
# or
make dev
```

## Testing

```bash
# All tests
pytest app/tests/ -v

# Single test file
pytest app/tests/test_auth.py -v

# Single test function
pytest app/tests/test_auth.py::test_function_name -v

# With coverage
make test-cov
```

## Linting & Formatting

```bash
make lint-check    # check without changes (black + isort + flake8)
make lint-apply    # apply formatting (black + isort)
```

## Database Migrations

```bash
alembic upgrade head                            # apply all pending migrations
alembic revision --autogenerate -m "message"    # generate from model changes

# or via make
make db-autogenerate MSG="description"
make db-upgrade
```

Always review generated migration files in `app/alembic/versions/` before applying.
