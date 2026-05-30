#!/bin/bash
cd backend
echo "=== Starting Celery Worker ==="
exec /opt/venv/bin/celery -A app.workers.celery_app.celery_app worker \
  --loglevel=info \
  --concurrency=2 \
  --queues=default,scanning,analysis
