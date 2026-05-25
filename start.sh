#!/bin/bash
# Non-fatal startup init — uvicorn always starts even if init has warnings
cd backend

echo "=== Running startup initialization ==="
/opt/venv/bin/python startup.py || echo "[start.sh] startup.py had errors, continuing to server..."

echo "=== Starting API server ==="
exec /opt/venv/bin/uvicorn main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers 4 \
  --log-level info
