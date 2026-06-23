"""
In-process APScheduler — replaces Celery Beat for Railway deployments.

Runs inside the uvicorn process. Uses a PostgreSQL-backed job store so that
across the 4 uvicorn workers only ONE worker actually executes each job
(SQLAlchemy job store uses DB-level locking for coordination).

Schedule (Asia/Jerusalem timezone):
  Sunday 07:00  — load_universe            (refresh S&P500+S&P400 from Wikipedia)
  Daily  07:30  — earnings_watcher         (only during earnings seasons; ≥20 fresh stocks → trigger quarterly scan)
  כל 30 דק'    — ta_scan                  (TA for all 50 master-list stocks — free, no Claude)
  Every 30 min  — news_watcher             (news+social for master-list stocks → alerts to holders)
  Daily  12:00  — quarterly_scan_batch     (processes 50 universe stocks/day when quarterly scan is active)

Quarterly flow:
  1. earnings_watcher detects ≥20 stocks with verified fresh earnings
  2. Triggers quarterly_scanner.trigger_quarterly_scan() → loads all ~900 stocks into Redis queue
  3. quarterly_scan_batch runs daily at 12:00, processes 50 stocks/day (~18 days for full universe)
  4. When queue empty → admin is notified → admin reviews and publishes Master List via Fund Dashboard
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


async def job_daily_ta_scan():
    """
    Daily 08:30 IL — run technical analysis (pandas-ta, no Claude) for all
    active master list stocks. Stores results so the frontend always shows
    fresh signals without requiring a quarterly scan.
    """
    from app.core.database import AsyncSessionLocal
    from app.db.models.master_list import MasterListEntry
    from app.db.models.asset import Asset
    from app.agents.workflow import run_technical_workflow
    from sqlalchemy import select

    logger.info("[scheduler] daily_ta_scan started")
    try:
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(MasterListEntry.symbol).where(MasterListEntry.is_active == True).distinct()
            )
            symbols = [r[0] for r in rows.all()]

        if not symbols:
            logger.info("[scheduler] daily_ta_scan: no active master list symbols — skipping")
            return

        logger.info(f"[scheduler] daily_ta_scan: scanning TA for {len(symbols)} symbols")
        success = errors = 0

        for symbol in symbols:
            try:
                async with AsyncSessionLocal() as db:
                    asset = (
                        await db.execute(select(Asset).where(Asset.symbol == symbol))
                    ).scalar_one_or_none()
                exchange = asset.exchange.value if asset else "NASDAQ"

                await run_technical_workflow(symbol=symbol, exchange=exchange)
                success += 1
            except Exception as e:
                errors += 1
                logger.warning(f"[scheduler] daily_ta_scan failed for {symbol}: {e}")

            await asyncio.sleep(0.5)  # gentle rate limit

        logger.info(f"[scheduler] daily_ta_scan done: success={success}, errors={errors}")
    except Exception as exc:
        logger.error(f"[scheduler] daily_ta_scan failed: {exc}")


# ─── Functions kept for manual / quarterly use (called from API endpoints) ───

async def job_run_prescreener():
    """
    Score ~900 universe stocks and activate the top 100 (80 LONG + 20 SHORT).
    Called manually by admin at the start of each quarterly scan cycle.
    """
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


async def job_run_full_scan(batch_size: int = 100):
    """
    Full Claude AI pipeline on active pool stocks.
    Called manually by admin during quarterly scan (100 stocks × 9 days).
    NOT scheduled automatically — triggered via Fund Dashboard.
    """
    from app.core.database import AsyncSessionLocal
    from app.db.models.asset import Asset
    from app.agents.workflow import run_investment_workflow
    from sqlalchemy import select

    logger.info(f"[scheduler] full_scan started (batch_size={batch_size})")
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Asset).where(Asset.is_active_in_pool == True))
            assets = result.scalars().all()

        if not assets:
            logger.warning("[scheduler] full_scan: no active pool stocks — run prescreener first")
            return {"scanned": 0, "approved": 0, "rejected": 0, "errors": 0}

        assets = assets[:batch_size]
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
            await asyncio.sleep(2)

        result = {"scanned": len(assets), "approved": approved, "rejected": rejected, "errors": errors}
        logger.info(f"[scheduler] full_scan done: {result}")
        return result
    except Exception as exc:
        logger.error(f"[scheduler] full_scan failed: {exc}")
        return {"error": str(exc)}


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
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": None,  # skip missed fires — no catch-up on restart
        },
        timezone="Asia/Jerusalem",
    )

    # Weekly universe refresh — Sunday 07:00 IL (free, scrapes Wikipedia)
    scheduler.add_job(
        job_load_universe,
        CronTrigger(day_of_week="sun", hour=7, minute=0, timezone="Asia/Jerusalem"),
        id="scheduled_load_universe",
        replace_existing=True,
    )

    # Daily earnings check — 07:30 IL
    # Monitors universe stocks for fresh earnings releases.
    # Accumulates in Redis queue; fires Claude scan when ≥ MIN_EARNINGS_TRIGGER stocks queued.
    from app.workers.earnings_watcher import job_earnings_queue_check
    scheduler.add_job(
        job_earnings_queue_check,
        CronTrigger(hour=7, minute=30, timezone="Asia/Jerusalem"),
        id="scheduled_earnings_watcher",
        replace_existing=True,
    )

    # Technical analysis — every 30 minutes (free: pandas-ta + yfinance, no Claude)
    # Covers all 50 Master List stocks each run to catch intraday signals.
    scheduler.add_job(
        job_daily_ta_scan,
        "interval",
        minutes=30,
        id="scheduled_ta_scan",
        replace_existing=True,
    )

    # News & social watcher — every 30 minutes (cheap, triggers TA on news)
    from app.workers.news_watcher import job_watch_news
    scheduler.add_job(
        job_watch_news,
        "interval",
        minutes=30,
        id="scheduled_news_watcher",
        replace_existing=True,
    )

    # Quarterly scan batch — 12:00 IL, every day
    # When a quarterly scan is active (triggered by earnings_watcher), processes
    # the next 50 universe stocks per day. Exits immediately when no scan is active.
    from app.workers.quarterly_scanner import job_quarterly_scan_batch
    scheduler.add_job(
        job_quarterly_scan_batch,
        CronTrigger(hour=12, minute=0, timezone="Asia/Jerusalem"),
        id="scheduled_quarterly_scan_batch",
        replace_existing=True,
    )

    return scheduler
