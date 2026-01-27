#!/bin/bash
# ============================================================================
# Sunbird AI API - Startup Script
# ============================================================================
# Runs database migrations and starts the FastAPI application
# Optimized for GCP Cloud Run deployment
# ============================================================================

set -e  # Exit on error
set -u  # Exit on undefined variable

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PORT="${PORT:-8080}"
WORKERS="${WORKERS:-4}"
HOST="${HOST:-0.0.0.0}"
LOG_LEVEL="${LOG_LEVEL:-info}"
TIMEOUT="${TIMEOUT:-120}"
KEEP_ALIVE="${KEEP_ALIVE:-5}"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Pre-flight checks
preflight_checks() {
    log_info "Running pre-flight checks..."

    # Check if Python is available
    if ! command -v python &> /dev/null; then
        log_error "Python is not installed"
        exit 1
    fi

    # Check if required environment variables are set
    if [ -z "${DATABASE_URL:-}" ]; then
        log_warning "DATABASE_URL not set, application may fail"
    fi

    log_success "Pre-flight checks passed"
}

# Run database migrations
run_migrations() {
    log_info "Running database migrations..."

    if ! command -v alembic &> /dev/null; then
        log_error "Alembic is not installed"
        exit 1
    fi

    # Run migrations with error handling
    if alembic upgrade head; then
        log_success "Database migrations completed successfully"
    else
        log_error "Database migrations failed"
        exit 1
    fi
}

# Start the application
start_application() {
    log_info "Starting Sunbird AI API..."
    log_info "Configuration:"
    log_info "  Host: ${HOST}"
    log_info "  Port: ${PORT}"
    log_info "  Workers: ${WORKERS}"
    log_info "  Log Level: ${LOG_LEVEL}"
    log_info "  Environment: ${ENVIRONMENT:-production}"

    # Start uvicorn with optimized settings for Cloud Run
    exec uvicorn app.api:app \
        --host "${HOST}" \
        --port "${PORT}" \
        --workers "${WORKERS}" \
        --log-level "${LOG_LEVEL}" \
        --timeout-keep-alive "${KEEP_ALIVE}" \
        --timeout-graceful-shutdown 30 \
        --no-access-log
}

# Main execution
main() {
    log_info "=========================================="
    log_info "Sunbird AI API - Startup"
    log_info "=========================================="

    # Run pre-flight checks
    preflight_checks

    # Run database migrations
    run_migrations

    # Start the application
    start_application
}

# Trap signals for graceful shutdown
trap 'log_warning "Received shutdown signal, stopping gracefully..."; exit 0' SIGTERM SIGINT

# Execute main function
main
