web: cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT --workers 4
worker: cd backend && celery -A app.workers.celery_app worker --loglevel=info --concurrency=4
beat: cd backend && celery -A app.workers.celery_app beat --loglevel=info
