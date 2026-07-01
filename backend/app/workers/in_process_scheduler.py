"""
In-process APScheduler — replaces Celery Beat for Railway deployments.

Runs inside the uvicorn process. Uses a PostgreSQL-backed job store so that
across the 4 uvicorn workers only ONE worker actually executes each job
(SQLAlchemy job store uses DB-level locking for coordination).

Schedule (Asia/Jerusalem timezone):
  Sunday 07:00  — load_universe         (refresh S&P500+S&P400 from Wikipedia)
  Daily  07:30  — earnings_watcher      (only during earnings seasons; ≥20 fresh → trigger quarterly scan)
  Every 30 min  — ta_scan               (TA for all 50 master-list stocks — free, no Claude)
  Every 30 min  — news_watcher          (news+social for master-list stocks → alerts to holders)
  Daily  08:00  — run_prescreener       (score ~900 stocks, activate top 100)
  Daily  09:00  — run_full_scan         (AI pipeline on 100 active stocks, 3 concurrent)
  Daily  12:00  — quarterly_scan_batch  (50 stocks/day when quarterly scan is active)

Quarterly flow:
  1. earnings_watcher detects ≥20 stocks with verified fresh earnings
  2. Triggers quarterly_scanner.trigger_quarterly_scan() → loads all ~900 stocks into Redis queue
  3. quarterly_scan_batch runs daily, processes 50 stocks/day (~18 days for full universe)
  4. When queue empty → admin notified → admin reviews and publishes Master List
"""
import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


# ─── Job functions ────────────────────────────────────────────────────────────

async def job_daily_ta_scan():
    """
    Every 30 min — TA scan for all active Master List stocks (pandas-ta + yfinance, no Claude).
    Sends alert to portfolio holders when signal changes within 4h cooldown.
    """
    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.db.models.master_list import MasterListEntry
    from app.db.models.asset import Asset
    from app.db.models.portfolio import Portfolio
    from app.db.models.notification import NotificationType
    from app.services.notifications.service import NotificationService
    from app.agents.workflow import run_technical_workflow
    from sqlalchemy import select
    import redis.asyncio as aioredis

    ACTIONABLE = {"BUY_NOW", "STRONG_BUY", "SELL_NOW", "STRONG_SELL"}
    SIGNAL_COOLDOWN_SEC = 4 * 3600
    SIGNAL_LABELS = {
        "BUY_NOW":     "📈 קנה",
        "STRONG_BUY":  "🚀 קנה חזק",
        "SELL_NOW":    "📉 מכור",
        "STRONG_SELL": "⚠️ מכור חזק",
    }

    redis_client = aioredis.from_url(settings.REDIS_URL)
    logger.info("[ta_scan] started")
    try:
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(MasterListEntry.symbol).where(MasterListEntry.is_active == True).distinct()
            )
            symbols = [r[0] for r in rows.all()]

        if not symbols:
            logger.info("[ta_scan] no active master list symbols — skipping")
            return

        logger.info(f"[ta_scan] scanning {len(symbols)} master list stocks")
        alerted = success = errors = 0

        for symbol in symbols:
            try:
                async with AsyncSessionLocal() as db:
                    asset = (await db.execute(select(Asset).where(Asset.symbol==symbol))).scalar_one_or_none()
                exchange = asset.exchange.value if asset else "NASDAQ"
                result = await run_technical_workflow(symbol=symbol, exchange=exchange)
                ta = result.get("technical_analysis") or {}
                signal = ta.get("timing_signal", "WAIT")
                success += 1

                if signal not in ACTIONABLE:
                    continue

                cooldown_key = f"investment_ai:ta_alert:{symbol}"
                last = await redis_client.get(cooldown_key)
                if last and last.decode() == signal:
                    continue

                async with AsyncSessionLocal() as db:
                    holders = await db.execute(
                        select(Portfolio.user_id).where(Portfolio.symbol==symbol, Portfolio.quantity>0).distinct()
                    )
                    user_ids = [r[0] for r in holders.all()]

                await redis_client.set(cooldown_key, signal, ex=SIGNAL_COOLDOWN_SEC)
                if not user_ids:
                    continue

                score = ta.get("technical_score", 0)
                price = ta.get("current_price")
                price_str = f" | מחיר: ${price:.2f}" if price else ""
                label = SIGNAL_LABELS.get(signal, signal)
                title = f"{label} — {symbol}{price_str} (ניתוח טכני, ציון {score:.0f}/100)"

                svc = NotificationService()
                async with AsyncSessionLocal() as db:
                    for uid in user_ids:
                        await svc.send_notification(
                            user_id=uid, recommendation_id=None,
                            internal_detail={"symbol": symbol, "signal": signal, "technical_score": score,
                                             "current_price": price, "trigger": "TA_SCAN"},
                            db=db, notification_type=NotificationType.ALERT, title=title,
                        )
                alerted += 1
                logger.info(f"[ta_scan] {symbol}: {signal} (score={score}) → {len(user_ids)} users")

            except Exception as e:
                errors += 1
                logger.warning(f"[ta_scan] {symbol} failed: {e}")
            await asyncio.sleep(0.5)

        logger.info(f"[ta_scan] done: success={success}, alerted={alerted}, errors={errors}")
    except Exception as exc:
        logger.error(f"[ta_scan] failed: {exc}")
    finally:
        await redis_client.aclose()


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
    """Daily 09:00 IL — full AI pipeline on all 100 active pool stocks (3 concurrent)."""
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
            "coalesce": True,       # collapse missed fire into one run
            "max_instances": 1,     # never run same job twice in parallel
            "misfire_grace_time": 3600,  # if server was down, still run within 1h
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

    # NOTE: pre_screener and full_scan are NOT scheduled daily.
    # They run quarterly via admin trigger or quarterly_scan_batch.
    # job_run_prescreener() and job_run_full_scan() remain available for manual/admin use.

    # Daily earnings check — 07:30 IL (only fires during 4 earnings seasons)
    from app.workers.earnings_watcher import job_earnings_queue_check
    scheduler.add_job(
        job_earnings_queue_check,
        CronTrigger(hour=7, minute=30, timezone="Asia/Jerusalem"),
        id="scheduled_earnings_watcher",
        replace_existing=True,
    )

    # Technical analysis scan — every 30 minutes (free: pandas-ta + yfinance, no Claude)
    scheduler.add_job(
        job_daily_ta_scan,
        "interval",
        minutes=30,
        id="scheduled_ta_scan",
        replace_existing=True,
    )

    # News & social watcher — every 30 minutes
    from app.workers.news_watcher import job_watch_news
    scheduler.add_job(
        job_watch_news,
        "interval",
        minutes=30,
        id="scheduled_news_watcher",
        replace_existing=True,
    )

    # Quarterly scan batch — 12:00 IL, every day (exits immediately if no scan active)
    from app.workers.quarterly_scanner import job_quarterly_scan_batch
    scheduler.add_job(
        job_quarterly_scan_batch,
        CronTrigger(hour=12, minute=0, timezone="Asia/Jerusalem"),
        id="scheduled_quarterly_scan_batch",
        replace_existing=True,
    )

    # Performance outcome tracking — daily 02:00 IL (off-hours, low impact)
    scheduler.add_job(
        job_track_outcomes,
        CronTrigger(hour=2, minute=0, timezone="Asia/Jerusalem"),
        id="scheduled_track_outcomes",
        replace_existing=True,
    )

    # Watchlist price alert check — every 10 minutes during market hours
    scheduler.add_job(
        job_check_price_alerts,
        "interval",
        minutes=10,
        id="scheduled_price_alerts",
        replace_existing=True,
    )

    # Daily portfolio snapshot — 18:00 IL (after US market close)
    scheduler.add_job(
        job_portfolio_snapshot,
        CronTrigger(hour=18, minute=0, timezone="Asia/Jerusalem"),
        id="scheduled_portfolio_snapshot",
        replace_existing=True,
    )

    return scheduler


async def job_track_outcomes():
    """Daily 02:00 IL — track WIN/LOSS/NEUTRAL outcomes for recommendations ≥30 days old."""
    from app.core.database import AsyncSessionLocal
    from app.services.performance_service import get_performance_service

    logger.info("[scheduler] track_outcomes started")
    try:
        svc = get_performance_service()
        async with AsyncSessionLocal() as db:
            result = await svc.track_pending_outcomes(db)
            await db.commit()
        logger.info(f"[scheduler] track_outcomes done: {result}")
    except Exception as exc:
        logger.error(f"[scheduler] track_outcomes failed: {exc}")


async def job_check_price_alerts():
    """Every 10 min — check watchlist price alerts, notify users on trigger."""
    from app.core.database import AsyncSessionLocal
    from app.services.performance_service import get_performance_service

    try:
        svc = get_performance_service()
        async with AsyncSessionLocal() as db:
            result = await svc.check_price_alerts(db)
            await db.commit()
        if result and result.get("triggered", 0) > 0:
            logger.info(f"[scheduler] price_alerts: {result['triggered']} triggered")
    except Exception as exc:
        logger.error(f"[scheduler] price_alerts failed: {exc}")


async def job_portfolio_snapshot():
    """Daily 18:00 IL — snapshot all user portfolio values for historical chart."""
    from app.core.database import AsyncSessionLocal
    from app.services.performance_service import get_performance_service

    try:
        svc = get_performance_service()
        async with AsyncSessionLocal() as db:
            result = await svc.take_portfolio_snapshot(db)
            await db.commit()
        logger.info(f"[scheduler] portfolio_snapshot done: {result}")
    except Exception as exc:
        logger.error(f"[scheduler] portfolio_snapshot failed: {exc}")
