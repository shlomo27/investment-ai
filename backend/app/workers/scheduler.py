"""
Celery Beat Scheduler
Defines the periodic task schedule for 24/7 market scanning.
"""
from celery.schedules import crontab
from app.workers.celery_app import celery_app

# Configure Beat schedule
celery_app.conf.beat_schedule = {
    # Scan entire asset pool every 5 minutes (24/7 - markets around the world)
    "scan-asset-pool-every-5-minutes": {
        "task": "scan_asset_pool",
        "schedule": 300.0,  # 5 minutes
        "options": {"queue": "scanning"},
    },

    # Scan user portfolios for sell signals every 5 minutes
    "scan-user-portfolios-every-5-minutes": {
        "task": "scan_user_portfolios",
        "schedule": 300.0,  # 5 minutes
        "options": {"queue": "scanning"},
    },

    # Update portfolio prices every 2 minutes during market hours
    "update-portfolio-prices-every-2-minutes": {
        "task": "update_portfolio_prices",
        "schedule": 120.0,  # 2 minutes
        "options": {"queue": "default"},
    },

    # Daily cleanup at 2 AM Israel time (UTC+3)
    "daily-cleanup": {
        "task": "cleanup_old_data",
        "schedule": crontab(hour=23, minute=0),  # 23:00 UTC = 02:00 IL
        "options": {"queue": "cleanup"},
    },

    # TASE market hours scan: Sunday-Thursday 9:00-17:00 IL time
    # We use the general scan above which runs 24/7; the agents handle
    # market-hours detection internally via the exchange field
}

celery_app.conf.timezone = "Asia/Jerusalem"
