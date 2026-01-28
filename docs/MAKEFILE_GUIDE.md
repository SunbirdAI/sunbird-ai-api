# Makefile Guide - Sunbird AI API

Comprehensive guide to using the Makefile for development, testing, and deployment.

## Quick Start

```bash
# See all available commands
make help

# Quick setup for new developers
make quickstart

# Run development server
make dev

# Run tests
make test
```

## Table of Contents

1. [Environment Setup](#environment-setup)
2. [Testing Commands](#testing-commands)
3. [Database & Migrations](#database--migrations)
4. [Running the Application](#running-the-application)
5. [Code Quality](#code-quality)
6. [Cleanup](#cleanup)
7. [Docker Commands](#docker-commands)
8. [Utility Commands](#utility-commands)
9. [CI/CD Commands](#cicd-commands)

---

## Environment Setup

### `make venv`
Create a Python virtual environment in the `env/` directory.

```bash
make venv
source env/bin/activate  # Activate the virtual environment
```

### `make install`
Install production dependencies from `requirements.txt`.

```bash
make install
```

### `make install-dev`
Install development dependencies including test tools (pytest, black, isort, flake8, mypy).

```bash
make install-dev
```

### `make setup`
Complete setup: creates virtual environment and installs all dependencies.

```bash
make setup
```

### `make quickstart`
Quick start for new developers: checks environment, installs dependencies, and runs migrations.

```bash
make quickstart
```

**What it does:**
1. Checks if `.env` file exists
2. Installs development dependencies
3. Runs database migrations
4. Shows next steps

---

## Testing Commands

### Basic Testing

#### `make test`
Run all tests with verbose output.

```bash
make test
```

#### `make test-unit`
Run only unit tests (excludes integration tests).

```bash
make test-unit
```

#### `make test-integration`
Run only integration tests.

```bash
make test-integration
```

### Advanced Testing

#### `make test-cov`
Run tests with coverage report (generates HTML and terminal reports).

```bash
make test-cov
# View HTML report: open htmlcov/index.html
```

#### `make test-verbose`
Run tests with very verbose output (shows print statements).

```bash
make test-verbose
```

#### `make test-fast`
Run tests with minimal output (fastest).

```bash
make test-fast
```

#### `make test-failed`
Re-run only the tests that failed in the last run.

```bash
make test-failed
```

#### `make test-watch`
Run tests in watch mode (requires pytest-watch).

```bash
make test-watch
```

### Specific Test Modules

#### `make test-api`
Run API tests only.

```bash
make test-api
```

#### `make test-auth`
Run authentication tests only.

```bash
make test-auth
```

#### `make test-routers`
Run all router tests.

```bash
make test-routers
```

#### `make test-services`
Run all service tests.

```bash
make test-services
```

---

## Database & Migrations

### View Database State

#### `make db-current`
Show the current database migration revision.

```bash
make db-current
```

#### `make db-history`
Show complete migration history with details.

```bash
make db-history
```

### Creating Migrations

#### `make db-revision MSG="description"`
Create a new empty migration file.

```bash
make db-revision MSG="add user table"
```

#### `make db-autogenerate MSG="description"`
Auto-generate a migration based on model changes.

```bash
make db-autogenerate MSG="add email field to users"
```

**Important:** Always review auto-generated migrations before applying!

#### `make db-migrate MSG="description"`
Create and apply migration in one step (autogenerate + upgrade).

```bash
make db-migrate MSG="add new feature"
```

### Applying Migrations

#### `make db-upgrade`
Upgrade database to the latest revision.

```bash
make db-upgrade
```

#### `make db-upgrade-step`
Upgrade database by one revision only.

```bash
make db-upgrade-step
```

### Rolling Back Migrations

#### `make db-downgrade`
Downgrade database by one revision.

```bash
make db-downgrade
```

#### `make db-downgrade-base`
Downgrade database to base (⚠️ **WARNING: may drop all data!**)

```bash
make db-downgrade-base
# You'll be prompted to confirm
```

### Other Database Commands

#### `make db-reset`
Reset database completely (downgrade to base, then upgrade to head).

```bash
make db-reset
```

#### `make db-stamp`
Stamp database with current revision without running migrations.

```bash
make db-stamp
```

### Migration Workflow Example

```bash
# 1. Make changes to your models
vim app/models/users.py

# 2. Generate migration
make db-autogenerate MSG="add last_login field"

# 3. Review the generated migration
vim app/alembic/versions/xxxxx_add_last_login_field.py

# 4. Apply migration
make db-upgrade

# 5. Verify
make db-current
```

---

## Running the Application

### `make dev` (or `make run` or `make start`)
Start development server with auto-reload on file changes.

```bash
make dev
# Server runs at http://0.0.0.0:8000
# API docs at http://0.0.0.0:8000/docs
```

**Features:**
- Auto-reload on code changes
- Debug mode enabled
- Runs on port 8000

### `make prod`
Start production server with multiple workers.

```bash
make prod
```

**Features:**
- Runs with 4 workers
- No auto-reload
- Production-optimized

**Before running in production:**
- Set `ENVIRONMENT=production` in `.env`
- Review security settings
- Configure proper database

### `make serve HOST=... PORT=...`
Start server with custom host and port.

```bash
make serve HOST=127.0.0.1 PORT=8080
```

---

## Code Quality

### Formatting & Linting

#### `make lint` (or `make lint-apply` or `make format`)
Apply code formatting (runs black + isort).

```bash
make lint
```

#### `make lint-check`
Check code style without making changes (CI-friendly).

```bash
make lint-check
```

### Individual Tools

#### `make black`
Run black formatter only.

```bash
make black
```

#### `make isort`
Run isort (import sorting) only.

```bash
make isort
```

#### `make flake8`
Run flake8 linter only.

```bash
make flake8
```

#### `make mypy`
Run mypy type checker.

```bash
make mypy
```

### Combined Checks

#### `make check`
Run all checks (lint + tests).

```bash
make check
```

---

## Cleanup

### `make clean`
Clean common artifacts (Python cache + test artifacts).

```bash
make clean
```

### `make clean-pyc`
Remove Python file artifacts only (`*.pyc`, `__pycache__`).

```bash
make clean-pyc
```

### `make clean-test`
Remove test and coverage artifacts only.

```bash
make clean-test
```

### `make clean-build`
Remove build artifacts only.

```bash
make clean-build
```

### `make clean-all`
Remove all artifacts (pyc + test + build).

```bash
make clean-all
```

---

## Docker Commands

### `make docker-build`
Build Docker image.

```bash
make docker-build
```

### `make docker-run`
Run application in Docker container.

```bash
make docker-run
```

### `make docker-stop`
Stop and remove Docker container.

```bash
make docker-stop
```

### `make docker-logs`
View Docker container logs (follows).

```bash
make docker-logs
```

### `make docker-shell`
Open a shell inside the running Docker container.

```bash
make docker-shell
```

---

## Utility Commands

### `make shell`
Start Python shell with application context loaded.

```bash
make shell
# Available: app, engine, async_session_maker, settings
```

### `make config`
Show current configuration (hides sensitive values).

```bash
make config
```

### `make check-env`
Check if `.env` file exists and is configured.

```bash
make check-env
```

### `make requirements` (or `make freeze`)
Generate `requirements.txt` from installed packages.

```bash
make requirements
```

---

## CI/CD Commands

### `make ci`
Run all CI checks (clean + lint-check + test).

```bash
make ci
```

### `make ci-test`
Run tests for CI with XML coverage report.

```bash
make ci-test
```

### `make ci-lint`
Run linting for CI.

```bash
make ci-lint
```

---

## Common Workflows

### Daily Development Workflow

```bash
# 1. Activate virtual environment
source env/bin/activate

# 2. Pull latest changes
git pull

# 3. Install/update dependencies
make install-dev

# 4. Run migrations
make db-upgrade

# 5. Run tests
make test

# 6. Start development server
make dev
```

### Adding a New Feature

```bash
# 1. Create feature branch
git checkout -b feature/my-feature

# 2. Make code changes
vim app/...

# 3. Create migration if needed
make db-migrate MSG="add my feature"

# 4. Format code
make lint

# 5. Run tests
make test

# 6. Commit and push
git add .
git commit -m "Add my feature"
git push
```

### Before Committing

```bash
# Run all checks
make check

# Or individual steps:
make lint        # Format code
make test        # Run tests
make lint-check  # Verify formatting
```

### CI/CD Pipeline

```bash
# Typical CI pipeline
make ci-lint     # Lint checks
make ci-test     # Run tests with coverage
make docker-build  # Build Docker image (if using Docker)
```

### Debugging Issues

```bash
# Run tests with verbose output
make test-verbose

# Run specific test module
make test-api

# Check configuration
make config

# Check database state
make db-current
make db-history

# Open Python shell
make shell
```

### Database Troubleshooting

```bash
# Check current state
make db-current

# View migration history
make db-history

# Reset database (development only!)
make db-reset

# Upgrade to specific revision
alembic upgrade <revision_id>
```

---

## Tips & Best Practices

### 1. Use Tab Completion
Makefile commands support tab completion in most shells.

### 2. Combine Commands
Chain commands for efficiency:
```bash
make clean && make lint && make test
```

### 3. Environment Variables
Override variables:
```bash
make serve HOST=127.0.0.1 PORT=3000
```

### 4. Quick Reference
Keep this guide handy or use:
```bash
make help
```

### 5. Always Review Migrations
Never blindly apply auto-generated migrations:
```bash
make db-autogenerate MSG="my changes"
# Review the generated file in app/alembic/versions/
make db-upgrade
```

### 6. Development vs Production
Development:
```bash
make dev  # Auto-reload, debug mode
```

Production:
```bash
make prod  # Multiple workers, optimized
```

### 7. Test Before Commit
Always run tests before committing:
```bash
make check  # Runs lint + tests
```

### 8. Clean Regularly
Keep your workspace clean:
```bash
make clean  # Remove Python cache and test artifacts
```

---

## Troubleshooting

### Command Not Found

**Problem:** `make: command not found`

**Solution:** Install make (macOS: `brew install make`, Linux: usually pre-installed)

### Permission Denied

**Problem:** Permission errors when running commands

**Solution:** Ensure virtual environment is activated:
```bash
source env/bin/activate
```

### Database Connection Errors

**Problem:** Cannot connect to database

**Solution:**
1. Check `.env` file exists: `make check-env`
2. Verify DATABASE_URL is correct
3. Ensure database server is running

### Migration Conflicts

**Problem:** Migration conflicts or errors

**Solution:**
```bash
# Check current state
make db-current

# View history
make db-history

# Reset if needed (development only!)
make db-reset
```

### Port Already in Use

**Problem:** Port 8000 already in use

**Solution:** Use custom port:
```bash
make serve PORT=8080
```

---

## Additional Resources

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Pytest Documentation](https://docs.pytest.org/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Database Configuration Guide](app/database/README.md)

---

## Getting Help

```bash
# Show all available commands
make help

# Check configuration
make config

# Run diagnostics
make check-env
```

For more help, check the project README or contact the development team.
