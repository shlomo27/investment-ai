#!/bin/bash
set -e

echo "=== Investment AI Platform Startup ==="

cd backend

echo "Running startup initialization..."
/opt/venv/bin/python startup.py

echo "Starting API server..."
exec /opt/venv/bin/uvicorn main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers "${WEB_WORKERS:-4}" \
  --log-level info
