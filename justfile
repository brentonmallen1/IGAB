# IGAB justfile — run `just` to see available commands

# ─── Setup ────────────────────────────────────────────────────────────────────

# Copy .env.example to .env if it doesn't exist
init:
    @[ -f .env ] || cp .env.example .env
    @echo "✓ .env ready (edit it before starting)"

# ─── Development ──────────────────────────────────────────────────────────────

# Start all services in dev mode (with live reload); tears down first if already running
dev:
    docker compose down --remove-orphans
    docker compose watch

# Start only the database container
dev-db:
    docker compose up db -d

# Run backend with live reload (reads DB creds from .env, connects to localhost)
dev-backend:
    #!/usr/bin/env bash
    set -a && source .env && set +a
    # bash mangles JSON arrays from .env; unset so pydantic-settings reads .env directly
    unset CORS_ORIGINS
    cd backend && uv sync && PYTHONPATH=src DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@localhost:${DB_PORT:-5432}/${DB_NAME}" \
        uv run uvicorn igab.main:app --host 0.0.0.0 --port 8000 --reload

# Run frontend dev server with HMR
dev-frontend:
    cd frontend && npm run dev

# Run Alembic migrations against the local database
dev-migrate:
    #!/usr/bin/env bash
    set -a && source .env && set +a
    unset CORS_ORIGINS
    cd backend && uv sync && PYTHONPATH=src DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@localhost:${DB_PORT:-5432}/${DB_NAME}" \
        uv run alembic upgrade head

# Start all services in Docker with live reload (original docker compose watch)
dev-docker:
    docker compose watch

# Start all services (no watch)
up:
    docker compose up

# Stop all services
down:
    docker compose down

# Rebuild all images
build:
    docker compose build

# Tail logs
logs service="":
    docker compose logs -f {{ service }}

# ─── Database ─────────────────────────────────────────────────────────────────

# Run Alembic migrations
migrate:
    docker compose exec api uv run alembic upgrade head

# Create a new migration
migration name:
    docker compose exec api uv run alembic revision --autogenerate -m "{{ name }}"

# Rollback last migration
rollback:
    docker compose exec api uv run alembic downgrade -1

# Drop and recreate the database (DESTRUCTIVE)
db-reset:
    docker compose exec db psql -U ${DB_USER:-igab} -c "DROP DATABASE IF EXISTS ${DB_NAME:-igab};"
    docker compose exec db psql -U ${DB_USER:-igab} -c "CREATE DATABASE ${DB_NAME:-igab};"
    just migrate

# Open psql shell
db-shell:
    docker compose exec db psql -U ${DB_USER:-igab} -d ${DB_NAME:-igab}

# ─── Backend ──────────────────────────────────────────────────────────────────

# Open a shell in the API container
api-shell:
    docker compose exec api bash

# Run backend tests with coverage report
test-backend:
    docker compose exec api uv run pytest --cov=igab --cov-report=term-missing

# Run backend linting
lint-backend:
    docker compose exec api uv run ruff check src/
    docker compose exec api uv run ruff format --check src/

# Format backend code
format-backend:
    docker compose exec api uv run ruff format src/

# Run pyright type checking
typecheck-backend:
    docker compose exec api uv run pyright src/

# Run all backend quality checks (lint + typecheck)
check-backend:
    just lint-backend
    just typecheck-backend

# Auto-fix ruff issues, format, then type-check with pyright (runs locally)
quality:
    cd backend && uv run ruff check --fix src/
    cd backend && uv run ruff format src/
    cd backend && uv run pyright src/

# ─── Frontend ─────────────────────────────────────────────────────────────────

# Open a shell in the frontend container
frontend-shell:
    docker compose exec frontend sh

# Run frontend type check
typecheck:
    docker compose exec frontend npm run typecheck

# Run frontend tests
test-frontend:
    docker compose exec frontend npm test

# ─── Production ───────────────────────────────────────────────────────────────

# Start in production mode (includes nginx)
prod:
    docker compose --profile production up -d

# ─── Utility ──────────────────────────────────────────────────────────────────

# Show running containers
ps:
    docker compose ps

# Remove all containers and volumes (DESTRUCTIVE)
clean:
    docker compose down -v --remove-orphans
