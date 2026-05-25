"""
Celery application configuration
Uses Redis as broker and result backend.
"""
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "investment_ai",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone
    timezone="Asia/Jerusalem",
    enable_utc=True,
    # Task settings
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    # Result expiry
    result_expires=3600,
    # Retry settings
    task_max_retries=3,
    task_default_retry_delay=60,
    # Routing
    task_default_queue="default",
    task_queues={
        "default": {},
        "high_priority": {},
        "scanning": {},
        "cleanup": {},
    },
    # Beat schedule is defined in scheduler.py
)


def get_celery_app() -> Celery:
    return celery_app
