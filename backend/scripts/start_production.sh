#!/usr/bin/env bash
# ==============================================================================
# EVCharge-Opt — Production Container Startup Script for Render
# ==============================================================================
set -e

echo "🚀 [STARTUP] Initializing EVCharge-Opt production service..."

# 1. Apply database migrations to PostgreSQL
echo "📦 [MIGRATION] Applying Alembic schema migrations..."
(cd backend && alembic upgrade head)

# 2. Seed baseline stations and grid groups idempotently
echo "🌱 [SEED] Checking & seeding baseline demonstration data..."
python backend/scripts/seed_data.py

# 3. Determine host and port
BIND_PORT="${PORT:-8002}"
BIND_HOST="${APP_HOST:-0.0.0.0}"

echo "⚡ [SERVER] Launching Uvicorn server on ${BIND_HOST}:${BIND_PORT}..."
exec uvicorn app.main:app --app-dir backend --host "${BIND_HOST}" --port "${BIND_PORT}"
