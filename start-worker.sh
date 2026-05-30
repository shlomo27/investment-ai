#!/bin/bash
cd backend

# Import beat schedule
/opt/venv/bin/python -c "import app.workers.scheduler" 2>/dev/null || true

echo "=== Starting Celery Worker + Beat Scheduler ==="
exec /opt/venv/bin/celery -A app.workers.celery_app.celery_app worker \
  --beat \
  --loglevel=info \
  --concurrency=2 \
  --queues=default,scanning,analysis,cleanup \
  --scheduler celery.beat.PersistentScheduler
