"""
In-process APScheduler — replaces Celery Beat for Railway deployments.

Runs inside the uvicorn process. Uses a PostgreSQL-backed job store so that
across the 4 uvicorn workers only ONE worker actually executes each job
(SQLAlchemy job store uses DB-level locking for coordination).

Schedule (Asia/Jerusalem timezone):
  Sunday 07:00  — load_universe   (refresh S&P500+S&P400 from Wikipedia)
  Daily  08:00  — run_prescreener (score ~900 stocks, activate top 100)
  Daily  09:00  — run_full_scan   (AI pipeline on 100 active stocks, 3 concurrent)
  Every 30 min  — news_watcher    (scan news/Twitter for master list stocks → alerts)
"""
import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


# ─── Job functions ────────────────────────────────────────────────────────────

async def job_load_universe():
    """Sunday 07:00 IL — refresh S&P500+S&P400 constituent list from Wikipedia."""
    from app.core.database import AsyncSessionLocal
    from app.workers.universe_loader import load_universe
    logger.info("[scheduler] load_universe started")
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                result = await load_universe(db)
        logger.info(f"[scheduler] load_universe done: {result}")
    except Exception as exc:
        logger.error(f"[scheduler] load_universe failed: {exc}")


async def job_run_prescreener():
    """Daily 08:00 IL — score universe, activate top 80 LONG + 20 SHORT."""
    from app.core.database import AsyncSessionLocal
    from app.workers.pre_screener import run_pre_screener
    logger.info("[scheduler] pre_screener started")
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                result = await run_pre_screener(db)
        logger.info(f"[scheduler] pre_screener done: {result}")
    except Exception as exc:
        logger.error(f"[scheduler] pre_screener failed: {exc}")


async def job_run_full_scan():
    """Daily 09:00 IL — full AI pipeline on active pool stocks (capped by MAX_SCAN_STOCKS)."""
    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.db.models.asset import Asset
    from app.agents.workflow import run_investment_workflow
    from sqlalchemy import select

    logger.info("[scheduler] full_scan started")
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Asset).where(Asset.is_active_in_pool == True))
            assets = result.scalars().all()

        if not assets:
            logger.warning("[scheduler] full_scan: no active pool stocks — run prescreener first")
            return

        # Cap to MAX_SCAN_STOCKS to protect API token budget
        cap = settings.MAX_SCAN_STOCKS
        if len(assets) > cap:
            logger.info(f"[scheduler] full_scan: capping {len(assets)} → {cap} stocks (MAX_SCAN_STOCKS)")
            assets = assets[:cap]

        logger.info(f"[scheduler] full_scan: scanning {len(assets)} stocks")
        BATCH = 3
        approved = rejected = errors = 0

        for i in range(0, len(assets), BATCH):
            batch = assets[i: i + BATCH]
            results = await asyncio.gather(
                *[
                    run_investment_workflow(
                        symbol=a.symbol,
                        exchange=a.exchange.value,
                        direction_bias=getattr(a, "direction_bias", None),
                    )
                    for a in batch
                ],
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, Exception):
                    errors += 1
                    logger.warning(f"[scheduler] stock scan error: {r}")
                elif isinstance(r, dict):
                    status = r.get("workflow_status", "")
                    if status in ("completed", "saved"):
                        approved += 1
                    else:
                        rejected += 1
            await asyncio.sleep(2)  # brief pause between batches

        logger.info(
            f"[scheduler] full_scan done: scanned={len(assets)}, "
            f"approved={approved}, rejected={rejected}, errors={errors}"
        )
    except Exception as exc:
        logger.error(f"[scheduler] full_scan failed: {exc}")


# ─── Scheduler factory ────────────────────────────────────────────────────────

def create_scheduler(sync_db_url: str) -> AsyncIOScheduler:
    """
    Build an AsyncIOScheduler with a PostgreSQL job store.
    The SQLAlchemy job store uses DB-level row locking so that across
    multiple uvicorn workers, each job runs exactly once.
    """
    jobstore = SQLAlchemyJobStore(url=sync_db_url)

    scheduler = AsyncIOScheduler(
        jobstores={"default": jobstore},
        job_defaults={
            "coalesce": True,    # collapse missed fires into one run
            "max_instances": 1,  # never run same job twice in parallel
            "misfire_grace_time": None,  # skip missed fires — prevents scan on every deploy
        },
        timezone="Asia/Jerusalem",
    )

    # Weekly universe refresh — Sunday 07:00 IL
    scheduler.add_job(
        job_load_universe,
        CronTrigger(day_of_week="sun", hour=7, minute=0, timezone="Asia/Jerusalem"),
        id="scheduled_load_universe",
        replace_existing=True,
    )

    # Daily pre-screener — 08:00 IL
    scheduler.add_job(
        job_run_prescreener,
        CronTrigger(hour=8, minute=0, timezone="Asia/Jerusalem"),
        id="scheduled_prescreener",
        replace_existing=True,
    )

    # Daily full AI scan — 09:00 IL (1 hour after pre-screener)
    scheduler.add_job(
        job_run_full_scan,
        CronTrigger(hour=9, minute=0, timezone="Asia/Jerusalem"),
        id="scheduled_full_scan",
        replace_existing=True,
    )

    # News & social watcher — every 30 minutes around the clock
    from app.workers.news_watcher import job_watch_news
    scheduler.add_job(
        job_watch_news,
        "interval",
        minutes=30,
        id="scheduled_news_watcher",
        replace_existing=True,
    )

    return scheduler
