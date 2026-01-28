# ============================================================================
# Sunbird AI API - Makefile
# ============================================================================
# Comprehensive commands for development, testing, and deployment
# ============================================================================

.PHONY: help
.DEFAULT_GOAL := help

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

# Variables
# Use virtual environment if available, otherwise use system
VENV_BIN := $(shell if [ -d env/bin ]; then echo env/bin/; fi)
PYTHON := $(VENV_BIN)python
PYTEST := $(VENV_BIN)pytest
ALEMBIC := $(VENV_BIN)alembic
UVICORN := $(VENV_BIN)uvicorn
BLACK := $(VENV_BIN)black
ISORT := $(VENV_BIN)isort
FLAKE8 := $(VENV_BIN)flake8
PIP := $(VENV_BIN)pip

# ============================================================================
# Help
# ============================================================================

help: ## Show this help message
	@echo "$(BLUE)Sunbird AI API - Available Commands$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-30s$(NC) %s\n", $$1, $$2}'
	@echo ""

# ============================================================================
# Environment Setup
# ============================================================================

.PHONY: install install-dev venv setup

venv: ## Create virtual environment
	@echo "$(BLUE)Creating virtual environment...$(NC)"
	$(PYTHON) -m venv env
	@echo "$(GREEN)✓ Virtual environment created$(NC)"
	@echo "$(YELLOW)Run 'source env/bin/activate' to activate$(NC)"

install: ## Install production dependencies
	@echo "$(BLUE)Installing production dependencies...$(NC)"
	$(PIP) install -r requirements.txt
	@echo "$(GREEN)✓ Dependencies installed$(NC)"

install-dev: ## Install development dependencies (includes test tools)
	@echo "$(BLUE)Installing development dependencies...$(NC)"
	$(PIP) install -r requirements.txt
	$(PIP) install pytest pytest-asyncio pytest-cov black isort flake8 mypy
	@echo "$(GREEN)✓ Development dependencies installed$(NC)"

setup: venv install-dev ## Complete setup (create venv + install all dependencies)
	@echo "$(GREEN)✓ Setup complete!$(NC)"
	@echo "$(YELLOW)Run 'source env/bin/activate' to activate the virtual environment$(NC)"

# ============================================================================
# Testing
# ============================================================================

.PHONY: test test-unit test-integration test-cov test-watch test-verbose test-fast

test: ## Run all tests
	@echo "$(BLUE)Running all tests...$(NC)"
	$(PYTEST) app/tests/ -v
	@echo "$(GREEN)✓ Tests completed$(NC)"

test-unit: ## Run unit tests only
	@echo "$(BLUE)Running unit tests...$(NC)"
	$(PYTEST) app/tests/ -v -m "not integration"
	@echo "$(GREEN)✓ Unit tests completed$(NC)"

test-integration: ## Run integration tests only
	@echo "$(BLUE)Running integration tests...$(NC)"
	$(PYTEST) app/tests/ -v -m integration
	@echo "$(GREEN)✓ Integration tests completed$(NC)"

test-cov: ## Run tests with coverage report
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	$(PYTEST) app/tests/ --cov=app --cov-report=html --cov-report=term-missing
	@echo "$(GREEN)✓ Coverage report generated$(NC)"
	@echo "$(YELLOW)Open htmlcov/index.html to view detailed coverage$(NC)"

test-verbose: ## Run tests with verbose output
	@echo "$(BLUE)Running tests with verbose output...$(NC)"
	$(PYTEST) app/tests/ -vv -s

test-watch: ## Run tests in watch mode (requires pytest-watch)
	@echo "$(BLUE)Running tests in watch mode...$(NC)"
	ptw app/tests/

test-fast: ## Run tests with minimal output (fast)
	@echo "$(BLUE)Running fast tests...$(NC)"
	$(PYTEST) app/tests/ -q --tb=line

test-failed: ## Re-run only failed tests
	@echo "$(BLUE)Re-running failed tests...$(NC)"
	$(PYTEST) app/tests/ --lf -v

# Specific test modules
test-api: ## Run API tests
	@echo "$(BLUE)Running API tests...$(NC)"
	$(PYTEST) app/tests/test_api.py -v

test-auth: ## Run authentication tests
	@echo "$(BLUE)Running authentication tests...$(NC)"
	$(PYTEST) app/tests/test_auth.py -v

test-routers: ## Run router tests
	@echo "$(BLUE)Running router tests...$(NC)"
	$(PYTEST) app/tests/test_routers/ -v

test-services: ## Run service tests
	@echo "$(BLUE)Running service tests...$(NC)"
	$(PYTEST) app/tests/test_services/ -v

# ============================================================================
# Database & Migrations (Alembic)
# ============================================================================

.PHONY: db-migrate db-upgrade db-downgrade db-current db-history db-reset db-revision db-autogenerate

db-current: ## Show current database revision
	@echo "$(BLUE)Current database revision:$(NC)"
	$(ALEMBIC) current

db-history: ## Show migration history
	@echo "$(BLUE)Migration history:$(NC)"
	$(ALEMBIC) history --verbose

db-revision: ## Create a new empty migration (use: make db-revision MSG="description")
	@echo "$(BLUE)Creating new migration...$(NC)"
	@if [ -z "$(MSG)" ]; then \
		echo "$(RED)Error: Please provide a message$(NC)"; \
		echo "Usage: make db-revision MSG=\"your message\""; \
		exit 1; \
	fi
	$(ALEMBIC) revision -m "$(MSG)"
	@echo "$(GREEN)✓ Migration created$(NC)"

db-autogenerate: ## Auto-generate migration from model changes (use: make db-autogenerate MSG="description")
	@echo "$(BLUE)Auto-generating migration...$(NC)"
	@if [ -z "$(MSG)" ]; then \
		echo "$(RED)Error: Please provide a message$(NC)"; \
		echo "Usage: make db-autogenerate MSG=\"your message\""; \
		exit 1; \
	fi
	$(ALEMBIC) revision --autogenerate -m "$(MSG)"
	@echo "$(GREEN)✓ Migration generated$(NC)"
	@echo "$(YELLOW)⚠ Please review the generated migration file!$(NC)"

db-upgrade: ## Upgrade database to latest revision
	@echo "$(BLUE)Upgrading database...$(NC)"
	$(ALEMBIC) upgrade head
	@echo "$(GREEN)✓ Database upgraded$(NC)"

db-upgrade-step: ## Upgrade database by one revision
	@echo "$(BLUE)Upgrading database by one step...$(NC)"
	$(ALEMBIC) upgrade +1
	@echo "$(GREEN)✓ Database upgraded$(NC)"

db-downgrade: ## Downgrade database by one revision
	@echo "$(BLUE)Downgrading database...$(NC)"
	$(ALEMBIC) downgrade -1
	@echo "$(GREEN)✓ Database downgraded$(NC)"

db-downgrade-base: ## Downgrade database to base (WARNING: drops all data)
	@echo "$(RED)⚠ WARNING: This will downgrade to base and may drop all data!$(NC)"
	@echo "Press Ctrl+C to cancel or Enter to continue..."
	@read dummy
	$(ALEMBIC) downgrade base
	@echo "$(GREEN)✓ Database downgraded to base$(NC)"

db-migrate: db-autogenerate db-upgrade ## Create and apply migration in one step (use: make db-migrate MSG="description")
	@echo "$(GREEN)✓ Migration created and applied$(NC)"

db-reset: db-downgrade-base db-upgrade ## Reset database (downgrade to base then upgrade to head)
	@echo "$(GREEN)✓ Database reset complete$(NC)"

db-stamp: ## Stamp database with current revision without running migrations
	@echo "$(BLUE)Stamping database...$(NC)"
	$(ALEMBIC) stamp head
	@echo "$(GREEN)✓ Database stamped$(NC)"

# ============================================================================
# Application
# ============================================================================

.PHONY: run dev start prod serve

run: dev ## Alias for dev

dev: ## Run development server with auto-reload
	@echo "$(BLUE)Starting development server...$(NC)"
	@echo "$(YELLOW)Server will auto-reload on file changes$(NC)"
	$(UVICORN) app.api:app --reload --host 0.0.0.0 --port 8000

start: dev ## Alias for dev

prod: ## Run production server
	@echo "$(BLUE)Starting production server...$(NC)"
	@echo "$(YELLOW)Make sure ENVIRONMENT=production in .env$(NC)"
	$(UVICORN) app.api:app --host 0.0.0.0 --port 8000 --workers 4

serve: ## Run server with custom host and port (use: make serve HOST=0.0.0.0 PORT=8080)
	@echo "$(BLUE)Starting server...$(NC)"
	$(UVICORN) app.api:app --host $(or $(HOST),0.0.0.0) --port $(or $(PORT),8000)

# ============================================================================
# Code Quality & Linting
# ============================================================================

.PHONY: lint lint-check lint-apply format check black isort flake8 mypy

lint: lint-apply ## Alias for lint-apply

lint-check: ## Check code style without making changes
	@echo "$(BLUE)Checking code style...$(NC)"
	@echo "$(YELLOW)Running black...$(NC)"
	$(BLACK) --check .
	@echo "$(YELLOW)Running isort...$(NC)"
	$(ISORT) --check-only .
	@echo "$(YELLOW)Running flake8...$(NC)"
	$(FLAKE8) .
	@echo "$(GREEN)✓ All style checks passed$(NC)"

lint-apply: ## Apply code formatting (black + isort)
	@echo "$(BLUE)Applying code formatting...$(NC)"
	@echo "$(YELLOW)Running black...$(NC)"
	$(BLACK) .
	@echo "$(YELLOW)Running isort...$(NC)"
	$(ISORT) .
	@echo "$(GREEN)✓ Code formatting applied$(NC)"

format: lint-apply ## Alias for lint-apply

black: ## Run black formatter only
	@echo "$(BLUE)Running black...$(NC)"
	$(BLACK) .
	@echo "$(GREEN)✓ Black formatting applied$(NC)"

isort: ## Run isort only
	@echo "$(BLUE)Running isort...$(NC)"
	$(ISORT) .
	@echo "$(GREEN)✓ Import sorting applied$(NC)"

flake8: ## Run flake8 linter only
	@echo "$(BLUE)Running flake8...$(NC)"
	$(FLAKE8) .

mypy: ## Run mypy type checker
	@echo "$(BLUE)Running mypy type checker...$(NC)"
	mypy app/
	@echo "$(GREEN)✓ Type checking complete$(NC)"

check: lint-check test ## Run all checks (lint + tests)
	@echo "$(GREEN)✓ All checks passed$(NC)"

# ============================================================================
# Cleanup
# ============================================================================

.PHONY: clean clean-pyc clean-test clean-build clean-all

clean-pyc: ## Remove Python file artifacts
	@echo "$(BLUE)Cleaning Python artifacts...$(NC)"
	find . -type f -name '*.py[co]' -delete
	find . -type d -name __pycache__ -delete
	@echo "$(GREEN)✓ Python artifacts cleaned$(NC)"

clean-test: ## Remove test and coverage artifacts
	@echo "$(BLUE)Cleaning test artifacts...$(NC)"
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -f coverage.xml
	@echo "$(GREEN)✓ Test artifacts cleaned$(NC)"

clean-build: ## Remove build artifacts
	@echo "$(BLUE)Cleaning build artifacts...$(NC)"
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	@echo "$(GREEN)✓ Build artifacts cleaned$(NC)"

clean: clean-pyc clean-test ## Clean common artifacts (pyc + test)
	@echo "$(GREEN)✓ Cleanup complete$(NC)"

clean-all: clean clean-build ## Remove all artifacts including build
	@echo "$(GREEN)✓ Deep cleanup complete$(NC)"

# ============================================================================
# Docker
# ============================================================================

.PHONY: docker-build docker-run docker-stop docker-logs docker-shell docker-compose-up docker-compose-down

docker-build: ## Build Docker image
	@echo "$(BLUE)Building Docker image...$(NC)"
	docker build -t sunbird-ai-api .
	@echo "$(GREEN)✓ Docker image built$(NC)"

docker-run: ## Run application in Docker
	@echo "$(BLUE)Running Docker container...$(NC)"
	docker run -d --name sunbird-api -p 8000:8080 --env-file .env sunbird-ai-api
	@echo "$(GREEN)✓ Container started at http://localhost:8000$(NC)"

docker-stop: ## Stop Docker container
	@echo "$(BLUE)Stopping Docker container...$(NC)"
	docker stop sunbird-api 2>/dev/null || true
	docker rm sunbird-api 2>/dev/null || true
	@echo "$(GREEN)✓ Container stopped$(NC)"

docker-logs: ## View Docker container logs
	docker logs -f sunbird-api

docker-shell: ## Open shell in Docker container
	docker exec -it sunbird-api /bin/bash

docker-compose-up: ## Start all services with docker-compose
	@echo "$(BLUE)Starting services with docker-compose...$(NC)"
	docker-compose up -d
	@echo "$(GREEN)✓ Services started$(NC)"
	@echo "$(YELLOW)API: http://localhost:8000$(NC)"
	@echo "$(YELLOW)DB: postgresql://postgres:postgres@localhost:5432/sunbirdai$(NC)"

docker-compose-down: ## Stop all docker-compose services
	@echo "$(BLUE)Stopping docker-compose services...$(NC)"
	docker-compose down
	@echo "$(GREEN)✓ Services stopped$(NC)"

docker-compose-logs: ## View docker-compose logs
	docker-compose logs -f

docker-push: ## Push Docker image to GCR (use: make docker-push PROJECT=your-project)
	@if [ -z "$(PROJECT)" ]; then \
		echo "$(RED)Error: Please provide PROJECT$(NC)"; \
		echo "Usage: make docker-push PROJECT=your-gcp-project"; \
		exit 1; \
	fi
	@echo "$(BLUE)Tagging and pushing image to GCR...$(NC)"
	docker tag sunbird-ai-api gcr.io/$(PROJECT)/sunbird-ai-api
	docker push gcr.io/$(PROJECT)/sunbird-ai-api
	@echo "$(GREEN)✓ Image pushed to gcr.io/$(PROJECT)/sunbird-ai-api$(NC)"

# ============================================================================
# Utility Commands
# ============================================================================

.PHONY: shell config check-env requirements freeze

shell: ## Start Python shell with app context
	@echo "$(BLUE)Starting Python shell...$(NC)"
	$(PYTHON) -i -c "from app.api import app; from app.database.db import engine, async_session_maker; from app.core.config import settings; print('App context loaded. Available: app, engine, async_session_maker, settings')"

config: ## Show current configuration
	@echo "$(BLUE)Current Configuration:$(NC)"
	@$(PYTHON) -c "from app.core.config import settings; import json; print(json.dumps({k: str(v) if 'password' not in k.lower() and 'key' not in k.lower() and 'secret' not in k.lower() else '***' for k, v in settings.model_dump().items()}, indent=2))"

check-env: ## Check if .env file exists
	@echo "$(BLUE)Checking environment configuration...$(NC)"
	@if [ -f .env ]; then \
		echo "$(GREEN)✓ .env file found$(NC)"; \
		echo "$(YELLOW)Database URL configured: $$(grep -q DATABASE_URL .env && echo 'Yes' || echo 'No')$(NC)"; \
	else \
		echo "$(RED)✗ .env file not found$(NC)"; \
		echo "$(YELLOW)Copy .env.example to .env and configure it$(NC)"; \
		exit 1; \
	fi

requirements: ## Generate requirements.txt from installed packages
	@echo "$(BLUE)Generating requirements.txt...$(NC)"
	$(PIP) freeze > requirements.txt
	@echo "$(GREEN)✓ requirements.txt updated$(NC)"

freeze: requirements ## Alias for requirements

# ============================================================================
# CI/CD Commands
# ============================================================================

.PHONY: ci ci-test ci-lint

ci: clean lint-check test ## Run all CI checks
	@echo "$(GREEN)✓ All CI checks passed$(NC)"

ci-test: ## Run tests for CI (with XML coverage)
	@echo "$(BLUE)Running CI tests...$(NC)"
	$(PYTEST) app/tests/ --cov=app --cov-report=xml --cov-report=term

ci-lint: lint-check ## Run linting for CI
	@echo "$(GREEN)✓ CI linting passed$(NC)"

# ============================================================================
# Quick Start
# ============================================================================

.PHONY: quickstart

quickstart: check-env install-dev db-upgrade ## Quick start for new developers
	@echo ""
	@echo "$(GREEN)✓ Setup complete!$(NC)"
	@echo ""
	@echo "$(BLUE)Next steps:$(NC)"
	@echo "  1. Review your .env configuration"
	@echo "  2. Run 'make test' to verify everything works"
	@echo "  3. Run 'make dev' to start the development server"
	@echo ""
	@echo "$(YELLOW)Useful commands:$(NC)"
	@echo "  make help          - Show all available commands"
	@echo "  make dev           - Start development server"
	@echo "  make test          - Run tests"
	@echo "  make db-migrate    - Create and apply database migration"
	@echo ""
