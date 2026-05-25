#!/bin/bash
set -e

echo "Starting AI Investment Platform..."

cd backend
exec /opt/venv/bin/uvicorn main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers "${WEB_WORKERS:-4}" \
  --log-level info
