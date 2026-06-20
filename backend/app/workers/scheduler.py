"""
Celery Beat Scheduler
Defines the periodic task schedule for market scanning.

Scan strategy:
  - Daily deep scan at 12:00 Israel time (09:00 UTC) — full AI pipeline
  - Price watchdog every 15 min — detects sudden price moves (no AI)
  - News watchdog every 30 min — detects breaking news (no AI)
  - Event-triggered scans fire immediately when watchdogs detect anomalies
"""
from celery.schedules import crontab
from app.workers.celery_app import celery_app

# Configure Beat schedule
celery_app.conf.beat_schedule = {
    # Daily deep scan at 12:00 Israel time (09:00 UTC)
    "scan-asset-pool-daily-noon": {
        "task": "scan_asset_pool",
        "schedule": crontab(hour=9, minute=0),  # 09:00 UTC = 12:00 IL
        "options": {"queue": "scanning"},
    },

    # Daily portfolio scan at 12:05 Israel time (staggered 5 min after asset pool)
    "scan-user-portfolios-daily-noon": {
        "task": "scan_user_portfolios",
        "schedule": crontab(hour=9, minute=5),  # 09:05 UTC = 12:05 IL
        "options": {"queue": "scanning"},
    },

    # Price watchdog every 15 minutes — cheap yfinance only, no AI
    "price-watchdog-every-15min": {
        "task": "check_price_movements",
        "schedule": 900.0,  # 15 minutes
        "options": {"queue": "default"},
    },

    # News watchdog every 30 minutes — headlines only, no AI
    "news-watchdog-every-30min": {
        "task": "check_breaking_news",
        "schedule": 1800.0,  # 30 minutes
        "options": {"queue": "default"},
    },

    # Update portfolio prices every 2 minutes during market hours
    "update-portfolio-prices-every-2-minutes": {
        "task": "update_portfolio_prices",
        "schedule": 120.0,  # 2 minutes
        "options": {"queue": "default"},
    },

    # Pre-screener at 08:00 Israel time (05:00 UTC) — scores universe, activates pool
    "pre-screener-daily-0800": {
        "task": "run_pre_screener",
        "schedule": crontab(hour=5, minute=0),  # 05:00 UTC = 08:00 IL
        "options": {"queue": "scanning"},
    },

    # Weekly universe refresh on Sunday 07:00 IL (04:00 UTC) — loads S&P500 + S&P400
    "universe-refresh-weekly-sunday": {
        "task": "load_universe",
        "schedule": crontab(hour=4, minute=0, day_of_week=0),  # Sunday 04:00 UTC = 07:00 IL
        "options": {"queue": "scanning"},
    },

    # Daily cleanup at 2 AM Israel time (UTC+3)
    "daily-cleanup": {
        "task": "cleanup_old_data",
        "schedule": crontab(hour=23, minute=0),  # 23:00 UTC = 02:00 IL
        "options": {"queue": "cleanup"},
    },
}

celery_app.conf.timezone = "Asia/Jerusalem"
