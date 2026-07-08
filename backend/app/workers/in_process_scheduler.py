"""
In-process APScheduler — replaces Celery Beat for Railway deployments.

Runs inside the uvicorn process. Only ONE of the 4 uvicorn workers starts the
scheduler — the worker that wins a PostgreSQL advisory lock in main.py's
lifespan (APScheduler 3.x has no cross-process coordination of its own; the
job store only persists jobs, it does not prevent duplicate fires).

Schedule (Asia/Jerusalem timezone):
  Sunday    07:00  — load_universe         (refresh S&P500+S&P400+TA-125 from Wikipedia)
  Daily     07:30  — earnings_watcher      (only during earnings seasons; ≥20 fresh → trigger quarterly scan)
  Daily     08:00  — pre_screener          (momentum-score universe → refresh active pool: top 80 LONG + 20 SHORT)
  Every 30min      — ta_scan               (TA for all master-list stocks — free, no Claude)
  Every 30min      — news_watcher          (news+social for master-list stocks → alerts to holders)
  Every 30min      — digest_sender         (batched external alerts for digest-mode users)
  Wednesday 09:00  — weekly_full_scan      (full Claude AI on ~100 active pool stocks — keeps recs fresh)
  Daily     12:00  — quarterly_scan_batch  (50 stocks/day when quarterly scan is active)

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
        # No explicit transaction wrapper: run_pre_screener manages its own
        # commits so the session doesn't idle in a transaction during the
        # minutes-long download phase.
        async with AsyncSessionLocal() as db:
            result = await run_pre_screener(db)
        logger.info(f"[scheduler] pre_screener done: {result}")
    except Exception as exc:
        logger.error(f"[scheduler] pre_screener failed: {exc}")


async def job_run_full_scan():
    """Weekly — Wednesday 09:00 IL — full AI pipeline on all 100 active pool stocks (3 concurrent)."""
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

        from app.workers.cost_guard import budget_exceeded, record_analysis_cost, get_today_spend
        from app.services.notifications.telegram_service import get_telegram_service

        logger.info(f"[scheduler] full_scan: scanning {len(assets)} stocks")
        BATCH = 3
        approved = rejected = errors = 0
        stopped_on_budget = False

        for i in range(0, len(assets), BATCH):
            if await budget_exceeded():
                spend = await get_today_spend()
                stopped_on_budget = True
                logger.warning(f"[scheduler] full_scan halted — daily budget hit (~${spend:.2f})")
                await get_telegram_service().send_admin_alert(
                    f"💰 <b>עצירת תקציב</b>\nהסריקה נעצרה — הגעת לתקרת ההוצאה היומית (~${spend:.2f}).\n"
                    f"נסרקו {approved + rejected + errors}/{len(assets)} מניות."
                )
                break

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
            await record_analysis_cost(len(batch))
            await asyncio.sleep(2)  # brief pause between batches

        logger.info(
            f"[scheduler] full_scan done: scanned={approved + rejected + errors}, "
            f"approved={approved}, rejected={rejected}, errors={errors}"
        )

        # Engine-down heuristic: a healthy scan produces a mix; if nearly
        # everything errored or fell through, a provider is likely down/out of
        # credit — alert admin instead of failing silently.
        total = approved + rejected + errors
        if not stopped_on_budget and total >= 10 and (errors + rejected) / total >= 0.9 and approved == 0:
            await get_telegram_service().send_admin_alert(
                f"⚠️ <b>אזהרת מנוע</b>\nסריקה שבועית הסתיימה עם 0 המלצות — "
                f"{errors} שגיאות, {rejected} נדחו מתוך {total}.\n"
                f"ייתכן שמנוע AI נפל או שנגמר קרדיט. בדוק לוגים + יתרות."
            )
    except Exception as exc:
        logger.error(f"[scheduler] full_scan failed: {exc}")


# ─── Scheduler factory ────────────────────────────────────────────────────────

def create_scheduler(sync_db_url: str) -> AsyncIOScheduler:
    """
    Build an AsyncIOScheduler with a PostgreSQL job store.
    NOTE: must only be started in ONE worker process — the caller (main.py
    lifespan) enforces this with a PostgreSQL advisory lock.
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

    # Daily pre-screener — 08:00 IL: momentum-score the universe, refresh the
    # active pool (top 80 LONG + 20 SHORT) that ta_scan and full_scan work on.
    scheduler.add_job(
        job_run_prescreener,
        CronTrigger(hour=8, minute=0, timezone="Asia/Jerusalem"),
        id="scheduled_prescreener",
        replace_existing=True,
    )

    # Weekly active-pool scan — every Wednesday 09:00 IL
    # Runs full Claude AI pipeline on all ~100 active pool stocks so recommendations
    # stay fresh between quarterly earnings seasons (events, rate changes, geopolitics).
    scheduler.add_job(
        job_run_full_scan,
        CronTrigger(day_of_week="wed", hour=9, minute=0, timezone="Asia/Jerusalem"),
        id="scheduled_weekly_full_scan",
        replace_existing=True,
    )

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

    # Digest sender — every 30 min, batches external alerts for digest-mode users
    scheduler.add_job(
        job_send_digests,
        "interval",
        minutes=30,
        id="scheduled_digest_sender",
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


async def dedupe_live_recommendations() -> int:
    """
    One-shot maintenance (called at startup by the scheduler-lock winner):
    keep only the NEWEST live (APPROVED/PRESENTED) recommendation per symbol,
    dismiss the rest. Cleans up duplicates created by pre-fix parallel
    schedulers. Idempotent — safe to run on every boot.
    """
    from sqlalchemy import select, update
    from app.core.database import AsyncSessionLocal
    from app.db.models.recommendation import Recommendation, RecommendationStatus

    live = [RecommendationStatus.APPROVED, RecommendationStatus.PRESENTED_TO_USER]
    dismissed = 0
    try:
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(Recommendation.id, Recommendation.symbol)
                .where(Recommendation.status.in_(live))
                .order_by(Recommendation.symbol, Recommendation.created_at.desc())
            )
            keep_seen: set[str] = set()
            to_dismiss: list[int] = []
            for rec_id, symbol in rows.all():
                if symbol in keep_seen:
                    to_dismiss.append(rec_id)
                else:
                    keep_seen.add(symbol)
            if to_dismiss:
                await db.execute(
                    update(Recommendation)
                    .where(Recommendation.id.in_(to_dismiss))
                    .values(status=RecommendationStatus.DISMISSED)
                )
                await db.commit()
                dismissed = len(to_dismiss)
                logger.info(f"[maintenance] dismissed {dismissed} duplicate live recommendations")
    except Exception as exc:
        logger.error(f"[maintenance] recommendation dedup failed: {exc}")
    return dismissed


async def job_send_digests():
    """
    Every 30 min — for users in digest mode (EVERY_4_HOURS / DAILY), send one
    generic external summary if new notifications accumulated since the last
    digest and the window has elapsed. Inbox rows are always real-time; this
    only batches the external push/SMS/email pings.
    """
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select, func
    from app.core.database import AsyncSessionLocal
    from app.db.models.user import User
    from app.db.models.notification import Notification
    from app.services.notifications.service import get_notification_service

    WINDOWS = {"EVERY_4_HOURS": timedelta(hours=4), "DAILY": timedelta(hours=24)}
    now = datetime.now(timezone.utc)
    svc = get_notification_service()
    sent = 0
    try:
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(User).where(User.is_active == True, User.alert_frequency.in_(list(WINDOWS)))
            )
            users = rows.scalars().all()

            for user in users:
                window = WINDOWS[user.alert_frequency]
                since = user.last_digest_sent_at or (now - window)
                if user.last_digest_sent_at and now - user.last_digest_sent_at < window:
                    continue

                count_row = await db.execute(
                    select(func.count(Notification.id)).where(
                        Notification.user_id == user.id,
                        Notification.sent_at > since,
                    )
                )
                pending = count_row.scalar() or 0
                if pending == 0:
                    continue

                channels = await svc.send_digest(user, pending)
                user.last_digest_sent_at = now
                sent += 1
                logger.info(f"[digest] user={user.id} pending={pending} channels={channels}")

            await db.commit()
        if sent:
            logger.info(f"[digest] done: {sent} digests sent")
    except Exception as exc:
        logger.error(f"[digest] failed: {exc}")


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
