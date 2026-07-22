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


# ─── Technical-signal alerting core ──────────────────────────────────────────

ACTIONABLE = {"BUY_NOW", "STRONG_BUY", "SELL_NOW", "STRONG_SELL"}
SIGNAL_COOLDOWN_SEC = 4 * 3600
SIGNAL_LABELS = {
    "BUY_NOW":     "📈 קנה",
    "STRONG_BUY":  "🚀 קנה חזק",
    "SELL_NOW":    "📉 מכור",
    "STRONG_SELL": "⚠️ מכור חזק",
}


async def process_signal_transition(symbol: str, ta: dict, redis_client=None) -> bool:
    """
    Shared alerting core for technical signals — fed by BOTH the 30-min scan
    and on-demand analyses (page opens/refreshes). A 30-min sampler can miss a
    short-lived flip that a user-triggered analysis catches on screen; routing
    every analysis through here means whatever the system SEES, holders HEAR.

    Tracks the previous signal per symbol, alerts holders on upgrades to an
    actionable signal AND on downgrades from one (momentum fading), applies
    the 4h same-signal cooldown. Returns True if an alert was sent.
    """
    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.db.models.portfolio import Portfolio
    from app.db.models.watchlist import Watchlist
    from app.db.models.notification import NotificationType
    from app.services.notifications.service import NotificationService
    from sqlalchemy import select
    import redis.asyncio as aioredis

    signal = (ta or {}).get("timing_signal", "WAIT")
    own_client = redis_client is None
    r = redis_client or aioredis.from_url(settings.REDIS_URL)
    try:
        last_signal_key = f"investment_ai:ta_last_signal:{symbol}"
        prev_raw = await r.get(last_signal_key)
        prev_signal = prev_raw.decode() if prev_raw else None
        await r.set(last_signal_key, signal, ex=7 * 24 * 3600)

        # Alert on TRANSITIONS only — a signal that merely persists past the
        # 4h cooldown must not re-alert ("קנה (קודם: קנה)" repeats confused
        # holders into thinking something changed).
        if prev_signal == signal:
            return False

        downgraded = prev_signal in ACTIONABLE and signal not in ACTIONABLE
        if signal not in ACTIONABLE and not downgraded:
            return False

        cooldown_key = f"investment_ai:ta_alert:{symbol}"
        last = await r.get(cooldown_key)
        if last and last.decode() == signal:
            return False

        async with AsyncSessionLocal() as db:
            holders = await db.execute(
                select(Portfolio.user_id).where(Portfolio.symbol == symbol, Portfolio.quantity > 0).distinct()
            )
            # Watchlist users who opted into technical alerts also get trend
            # changes — lets a user track a feed rec (e.g. ADBE) without
            # pretending to hold it.
            watchers = await db.execute(
                select(Watchlist.user_id).where(
                    Watchlist.symbol == symbol,
                    Watchlist.alert_on_technical_signal == True,
                ).distinct()
            )
            user_ids = list(
                {row[0] for row in holders.all()} | {row[0] for row in watchers.all()}
            )

        await r.set(cooldown_key, signal, ex=SIGNAL_COOLDOWN_SEC)
        if not user_ids:
            return False

        score = ta.get("technical_score", 0)
        price = ta.get("current_price")
        price_str = f" | מחיר נוכחי: ${price:.2f}" if price else ""

        # Entry-point moment: the stock has a LIVE BUY recommendation
        # (fundamental YES) and its technical just turned positive. That's the
        # "both agree" window a watcher waited for — frame it as such.
        entry_point = False
        if signal in ("BUY_NOW", "STRONG_BUY"):
            from app.db.models.recommendation import Recommendation, RecommendationStatus, RecommendationType
            async with AsyncSessionLocal() as db:
                live_buy = (await db.execute(
                    select(Recommendation.id).where(
                        Recommendation.symbol == symbol,
                        Recommendation.recommendation_type.in_(
                            [RecommendationType.BUY, RecommendationType.STRONG_BUY]
                        ),
                        Recommendation.status.in_([
                            RecommendationStatus.APPROVED,
                            RecommendationStatus.PRESENTED_TO_USER,
                            RecommendationStatus.ACTIONED,
                        ]),
                    ).limit(1)
                )).first()
            entry_point = live_buy is not None

        if downgraded:
            prev_label = SIGNAL_LABELS.get(prev_signal, prev_signal)
            # "היה X, עכשיו Y" — an inline arrow between Hebrew words is
            # direction-ambiguous in RTL and users misread the transition.
            title = (f"⬇️ {symbol}: הסיגנל נחלש — היה: {prev_label}, עכשיו: המתנה"
                     f"{price_str} (ניתוח טכני, ציון {score:.0f}/100)")
        elif entry_point:
            title = (f"🟢 {symbol}: נקודת הכניסה הגיעה — ההמלצה (קנייה) נפגשה עם סיגנל טכני חיובי. "
                     f"שני הצדדים מסכימים{price_str} (ציון טכני {score:.0f}/100). 👈 בדוק במערכת.")
        else:
            label = SIGNAL_LABELS.get(signal, signal)
            prev_str = f" (קודם: {SIGNAL_LABELS.get(prev_signal, 'המתנה')})" if prev_signal else ""
            title = f"{label} — {symbol}{price_str}{prev_str} (ניתוח טכני, ציון {score:.0f}/100)"

        svc = NotificationService()
        async with AsyncSessionLocal() as db:
            for uid in user_ids:
                await svc.send_notification(
                    user_id=uid, recommendation_id=None,
                    internal_detail={"symbol": symbol, "signal": signal,
                                     "previous_signal": prev_signal,
                                     "technical_score": score,
                                     "current_price": price, "trigger": "TA_SCAN"},
                    db=db, notification_type=NotificationType.ALERT, title=title,
                )
        logger.info(f"[ta_signal] {symbol}: {prev_signal or '—'}→{signal} (score={score}) → {len(user_ids)} users")
        return True
    finally:
        if own_client:
            await r.aclose()


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
    from app.db.models.recommendation import Recommendation, RecommendationStatus
    from app.agents.workflow import run_technical_workflow
    from sqlalchemy import select
    import redis.asyncio as aioredis

    LIVE_STATUSES = [
        RecommendationStatus.APPROVED,
        RecommendationStatus.PRESENTED_TO_USER,
        RecommendationStatus.ACTIONED,
    ]

    redis_client = aioredis.from_url(settings.REDIS_URL)
    logger.info("[ta_scan] started")
    try:
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(MasterListEntry.symbol).where(MasterListEntry.is_active == True).distinct()
            )
            master_symbols = {r[0] for r in rows.all()}
            # Also cover every stock users actually HOLD — a position bought
            # from a past master list must stay monitored even after the list
            # rotates. TA is free (no LLM), so the wider set costs nothing.
            held_rows = await db.execute(
                select(Portfolio.symbol).where(Portfolio.quantity > 0).distinct()
            )
            held_symbols = {r[0] for r in held_rows.all()}
            # And every stock with a LIVE recommendation in the signals feed —
            # otherwise a feed card's technical signal goes stale until the
            # user opens its technical page (ADBE showed WAIT on the card while
            # a fresh analysis said SELL).
            live_rows = await db.execute(
                select(Recommendation.symbol).where(
                    Recommendation.status.in_(LIVE_STATUSES)
                ).distinct()
            )
            live_symbols = {r[0] for r in live_rows.all()}

        symbols = sorted(master_symbols | held_symbols | live_symbols)
        if not symbols:
            logger.info("[ta_scan] no active master list symbols — skipping")
            return

        logger.info(
            f"[ta_scan] scanning {len(symbols)} stocks "
            f"(master={len(master_symbols)}, held-only={len(held_symbols - master_symbols)}, "
            f"live-rec-only={len(live_symbols - master_symbols - held_symbols)})"
        )
        alerted = success = errors = 0

        for symbol in symbols:
            try:
                async with AsyncSessionLocal() as db:
                    asset = (await db.execute(select(Asset).where(Asset.symbol==symbol))).scalar_one_or_none()
                exchange = asset.exchange.value if asset else "NASDAQ"
                result = await run_technical_workflow(symbol=symbol, exchange=exchange)
                ta = result.get("technical_analysis") or {}
                # yfinance rate-limits mid-batch on cloud IPs; a throttled fetch
                # returns empty and silently skips the stock. Retry once after a
                # short pause so held/feed positions aren't left unmonitored.
                if not ta:
                    await asyncio.sleep(3)
                    result = await run_technical_workflow(symbol=symbol, exchange=exchange)
                    ta = result.get("technical_analysis") or {}
                success += 1

                # Persist the fresh TA onto any live recommendation for this
                # symbol so the feed card + technical page reflect the latest
                # signal without the user having to open and re-run it.
                if ta:
                    async with AsyncSessionLocal() as db:
                        recs = (await db.execute(
                            select(Recommendation).where(
                                Recommendation.symbol == symbol,
                                Recommendation.status.in_(LIVE_STATUSES),
                            )
                        )).scalars().all()
                        for rec in recs:
                            rec.technical_analysis = ta
                        if recs:
                            await db.commit()

                if await process_signal_transition(symbol, ta, redis_client=redis_client):
                    alerted += 1

            except Exception as e:
                errors += 1
                logger.warning(f"[ta_scan] {symbol} failed: {e}")
            await asyncio.sleep(0.5)

        from datetime import datetime, timezone
        await redis_client.set(
            "investment_ai:ta_scan:heartbeat",
            f"{datetime.now(timezone.utc).isoformat()}|scanned={len(symbols)}|"
            f"success={success}|alerted={alerted}|errors={errors}",
            ex=7 * 24 * 3600,
        )
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
    from app.db.models.portfolio import Portfolio
    from app.db.models.recommendation import Recommendation, RecommendationStatus
    from app.agents.workflow import run_investment_workflow
    from sqlalchemy import select

    logger.info("[scheduler] full_scan started")
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Asset).where(Asset.is_active_in_pool == True))
            assets = list(result.scalars().all())
            pool_symbols = {a.symbol for a in assets}

            # A recommendation shown to users, or a stock a user actually holds,
            # must be re-analyzed weekly even after the prescreener rotates it
            # out of the active pool — otherwise stale cards linger in the feed
            # and holders never get a fresh fundamental read on their position.
            held_rows = await db.execute(
                select(Portfolio.symbol).where(Portfolio.quantity > 0).distinct()
            )
            live_rows = await db.execute(
                select(Recommendation.symbol)
                .where(
                    Recommendation.status.in_(
                        [
                            RecommendationStatus.APPROVED,
                            RecommendationStatus.PRESENTED_TO_USER,
                            RecommendationStatus.ACTIONED,
                        ]
                    )
                )
                .distinct()
            )
            extra_symbols = (
                {r[0] for r in held_rows.all()} | {r[0] for r in live_rows.all()}
            ) - pool_symbols
            if extra_symbols:
                extra_result = await db.execute(
                    select(Asset).where(Asset.symbol.in_(extra_symbols))
                )
                extra_assets = list(extra_result.scalars().all())
                assets.extend(extra_assets)
                logger.info(
                    f"[scheduler] full_scan: +{len(extra_assets)} held/live-rec stocks "
                    f"outside the pool ({sorted(a.symbol for a in extra_assets)})"
                )

            # Skip stocks with a fresh REAL analysis (last 14 days, confidence
            # > 0 — engine-down fallbacks don't count) UNLESS the company
            # reported earnings after that analysis. Earnings-driven analysis
            # is the primary engine now; the weekly scan fills gaps: new
            # momentum entrants and aging theses.
            from datetime import datetime as _dt, timezone as _tz, timedelta as _td
            from sqlalchemy import func as _f
            cutoff = _dt.now(_tz.utc) - _td(days=14)
            la_rows = await db.execute(
                select(Recommendation.symbol, _f.max(Recommendation.created_at))
                .where(Recommendation.confidence_score > 0)
                .group_by(Recommendation.symbol)
            )
            last_analysis = {r[0]: r[1] for r in la_rows.all()}

        report_dates = {}
        try:
            from app.workers.quarterly_scanner import _earnings_report_dates
            from app.core.config import settings as _settings
            import redis.asyncio as _aioredis
            _r = _aioredis.from_url(_settings.REDIS_URL)
            try:
                report_dates = await _earnings_report_dates(_r)
            finally:
                await _r.aclose()
        except Exception:
            pass

        def _recently_analyzed(sym: str) -> bool:
            la = last_analysis.get(sym)
            if la is None:
                return False
            la_utc = la if la.tzinfo else la.replace(tzinfo=_tz.utc)
            if la_utc < cutoff:
                return False
            rd = report_dates.get(sym)
            if rd and la_utc.date().isoformat() < rd:
                return False  # reported AFTER last analysis — must re-analyze
            return True

        skipped = [a.symbol for a in assets if _recently_analyzed(a.symbol)]
        assets = [a for a in assets if a.symbol not in set(skipped)]
        if skipped:
            logger.info(
                f"[scheduler] full_scan: skipping {len(skipped)} recently-analyzed stocks "
                f"(fresh analysis <14d, no newer earnings)"
            )

        if not assets:
            logger.info("[scheduler] full_scan: nothing to scan — all covered by recent analyses")
            return

        from app.workers.cost_guard import budget_exceeded, record_analysis_cost, get_today_spend
        from app.services.notifications.telegram_service import get_telegram_service

        from app.workers.cost_guard import (
            is_decision_engine_down, is_engine_down_result,
            mark_decision_engine_down, clear_decision_engine_down,
        )
        if await is_decision_engine_down():
            logger.warning("[scheduler] full_scan skipped — decision engine DOWN")
            return

        logger.info(f"[scheduler] full_scan: scanning {len(assets)} stocks")
        BATCH = 3
        approved = rejected = errors = 0
        stopped_on_budget = False
        engine_fail_streak = 0

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
            batch_engine_down = False
            for r in results:
                if isinstance(r, Exception):
                    errors += 1
                    logger.warning(f"[scheduler] stock scan error: {r}")
                elif isinstance(r, dict):
                    if is_engine_down_result(r):
                        batch_engine_down = True
                        continue
                    status = r.get("workflow_status", "")
                    if status in ("completed", "saved"):
                        approved += 1
                    else:
                        rejected += 1

            if batch_engine_down:
                engine_fail_streak += 1
                if engine_fail_streak >= 2:  # ~6 stocks all failing → engine down
                    await mark_decision_engine_down()
                    await get_telegram_service().send_admin_alert(
                        "⛔ <b>הסריקה השבועית נעצרה — מנוע הניתוח נפל</b>\n\n"
                        "Claude מחזיר שגיאה (כנראה קרדיטים). הסריקה נעצרה כדי לא "
                        "לייצר ניתוחים שגויים. טען קרדיטים והפעל auto top-up."
                    )
                    logger.error("[scheduler] full_scan halted — decision engine DOWN")
                    break
                await asyncio.sleep(2)
                continue

            engine_fail_streak = 0
            await clear_decision_engine_down()
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

        if approved:
            await maybe_nudge_master_list_publish()
    except Exception as exc:
        logger.error(f"[scheduler] full_scan failed: {exc}")


async def job_poll_telegram_links():
    """
    Every 30s — poll the bot for '/start <code>' messages sent from private
    chats and link that chat to the user account behind the one-time code
    (created by POST /auth/telegram/link-code). Personal alerts then go to
    the user's own chat instead of the shared channel.
    """
    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.db.models.user import User
    from app.services.notifications.telegram_service import get_telegram_service
    from sqlalchemy import select
    import httpx
    import redis.asyncio as aioredis

    token = settings.TELEGRAM_BOT_TOKEN
    if not token or token.startswith("your_"):
        return

    r = aioredis.from_url(settings.REDIS_URL)
    try:
        offset_raw = await r.get("investment_ai:tg_update_offset")
        params: dict = {"timeout": 0, "allowed_updates": '["message"]'}
        if offset_raw:
            params["offset"] = int(offset_raw)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"https://api.telegram.org/bot{token}/getUpdates", params=params
            )
            data = resp.json()
        if not data.get("ok"):
            return
        updates = data.get("result", [])
        if not updates:
            return
        await r.set("investment_ai:tg_update_offset", updates[-1]["update_id"] + 1)

        tg = get_telegram_service()
        for upd in updates:
            msg = upd.get("message") or {}
            chat = msg.get("chat") or {}
            text = (msg.get("text") or "").strip()
            if chat.get("type") != "private" or not text.startswith("/start"):
                continue
            chat_id = str(chat["id"])
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await tg.send_message(
                    "כדי לחבר את החשבון, לחץ על 'חבר טלגרם אישי' בהגדרות המערכת "
                    "והשתמש בקישור שנוצר.",
                    chat_id=chat_id,
                )
                continue
            code = parts[1].strip()
            uid_raw = await r.get(f"investment_ai:tg_link:{code}")
            if not uid_raw:
                await tg.send_message(
                    "⚠️ הקוד לא תקף או שפג תוקפו (10 דקות). "
                    "צור קישור חדש מהגדרות המערכת.",
                    chat_id=chat_id,
                )
                continue
            user_id = int(uid_raw)
            async with AsyncSessionLocal() as db:
                res = await db.execute(select(User).where(User.id == user_id))
                user = res.scalar_one_or_none()
                if not user:
                    continue
                user.telegram_chat_id = chat_id
                await db.commit()
                name = user.full_name
            await r.delete(f"investment_ai:tg_link:{code}")
            await tg.send_message(
                f"✅ <b>הטלגרם חובר בהצלחה!</b>\n\n"
                f"שלום {name}, מעכשיו תקבל כאן התרעות אישיות על התיק שלך — "
                f"שינויי מגמה בהחזקות והמלצות חדשות.",
                chat_id=chat_id,
            )
            logger.info(f"[tg_link] linked user {user_id} to chat {chat_id}")
    except Exception as exc:
        logger.warning(f"[tg_link] poll failed: {exc}")
    finally:
        await r.aclose()



async def maybe_nudge_master_list_publish():
    """
    After deep scans: if fresh live recommendations accumulated since the
    last master-list publish, remind the admin (once per 24h) that clients
    are still seeing the old list. Publishing stays a deliberate manual act —
    this only makes sure it is never forgotten.
    """
    from datetime import datetime, timezone

    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.db.models.master_list import MasterListEntry
    from app.db.models.recommendation import Recommendation, RecommendationStatus
    from app.services.notifications.telegram_service import get_telegram_service
    from sqlalchemy import select, func
    import redis.asyncio as aioredis

    r = aioredis.from_url(settings.REDIS_URL)
    try:
        NUDGE_KEY = "investment_ai:master_list_nudge"
        if await r.get(NUDGE_KEY):
            return  # already nudged within the last 24h

        async with AsyncSessionLocal() as db:
            last_pub = (
                await db.execute(select(func.max(MasterListEntry.published_at)))
            ).scalar()
            live = [
                RecommendationStatus.APPROVED,
                RecommendationStatus.PRESENTED_TO_USER,
                RecommendationStatus.ACTIONED,
            ]
            q = select(func.count(Recommendation.id)).where(Recommendation.status.in_(live))
            if last_pub:
                q = q.where(Recommendation.created_at > last_pub)
            new_count = (await db.execute(q)).scalar() or 0

        if new_count < 3:
            return  # not enough new material to bother the admin

        days = (datetime.now(timezone.utc) - last_pub).days if last_pub else None
        age_str = f"פורסמה לפני {days} ימים" if days is not None else "מעולם לא פורסמה"
        await get_telegram_service().send_admin_alert(
            f"📋 <b>ארכיון רשימת המאסטר מתיישן</b>\n\n"
            f"הלקוחות רואים את פיד הסיגנלים החי (מתעדכן לבד), אז הם לא נפגעים. "
            f"אבל רשימת המאסטר הרשמית שלך {age_str}, ומאז הצטברו "
            f"<b>{new_count}</b> המלצות חדשות בפיד.\n\n"
            f"אם תרצה תיעוד רשמי מעודכן: רשימת מאסטר ← \"פרסם רשימה חדשה\" (רשות)."
        )
        await r.set(NUDGE_KEY, "1", ex=24 * 3600)
        logger.info(f"[master_nudge] admin nudged: {new_count} new live recs since last publish")
    except Exception as exc:
        logger.warning(f"[master_nudge] failed: {exc}")
    finally:
        await r.aclose()


async def job_engine_health_check():
    """
    Every 6h — minimal ping to each of the 4 AI engines (Claude, GPT, Gemini,
    Grok). Alerts the ADMIN channel only on state transitions: engine went
    down (🔴 with the error) or recovered (🟢). Cost per round is a few dozen
    tokens per engine — negligible.
    """
    import asyncio as _asyncio

    from app.core.config import settings
    from app.services.notifications.telegram_service import get_telegram_service
    import redis.asyncio as aioredis

    async def _ping_claude() -> str | None:
        if not (settings.ANTHROPIC_API_KEY or "").strip():
            return None
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(model=settings.CLAUDE_MODEL, api_key=settings.ANTHROPIC_API_KEY,
                            max_tokens=8, temperature=0)
        await llm.ainvoke("ping")
        return "ok"

    async def _ping_gpt() -> str | None:
        if not (settings.OPENAI_API_KEY or "").strip():
            return None
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY,
                         max_tokens=8, temperature=0)
        await llm.ainvoke("ping")
        return "ok"

    async def _ping_gemini() -> str | None:
        if not (settings.GEMINI_API_KEY or "").strip():
            return None
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(model=settings.GEMINI_MODEL, google_api_key=settings.GEMINI_API_KEY,
                                     max_output_tokens=64, temperature=0)
        await llm.ainvoke("ping")
        return "ok"

    async def _ping_grok() -> str | None:
        if not (settings.XAI_API_KEY or "").strip():
            return None
        import httpx
        # A real (tiny) generation, so exhausted credits fail here too —
        # a models-list succeeds even with a $0 balance.
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.x.ai/v1/responses",
                headers={"Authorization": f"Bearer {settings.XAI_API_KEY}"},
                json={"model": settings.XAI_MODEL, "input": "ping", "max_output_tokens": 16},
            )
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:150]}")
        return "ok"

    def _diagnose(err: str) -> str:
        e = err.lower()
        if any(k in e for k in ("insufficient", "credit", "billing", "payment", "402", "balance")):
            return "💳 נגמרו הקרדיטים או בעיית חיוב — היכנס לחשבון הספק וטען/עדכן אמצעי תשלום"
        if any(k in e for k in ("invalid api key", "invalid x-api-key", "unauthorized", "authentication", "401", "403", "permission")):
            return "🔑 מפתח ה-API לא תקין או נחסם — בדוק את המשתנה ב-Railway מול המפתח אצל הספק"
        if any(k in e for k in ("429", "rate limit", "quota", "resource_exhausted", "resource exhausted")):
            return "⏳ חריגת מכסה/קצב — ייתכן שנגמרה המכסה (בגרסה חינמית) או עומס זמני; לרוב חולף תוך שעות"
        if any(k in e for k in ("not found", "404", "no such model", "decommissioned", "deprecated")):
            return "🏷️ שם המודל לא קיים אצל הספק — ייתכן שהוצא משימוש וצריך לעדכן את שם המודל"
        if any(k in e for k in ("timeout", "timed out", "connection", "unavailable", "overloaded", "500", "502", "503", "529")):
            return "🌐 תקלה זמנית בצד הספק — לרוב חולפת מעצמה; אם נמשכת מעל כמה שעות, בדוק את עמוד הסטטוס של הספק"
        return "❓ שגיאה לא מזוהה — ראה את הפירוט הטכני למעלה"

    ENGINES = {
        "Claude (ניתוח והחלטה)": _ping_claude,
        "GPT (חדשות)": _ping_gpt,
        "Gemini (מאקרו)": _ping_gemini,
        "Grok (סנטימנט X)": _ping_grok,
    }

    r = aioredis.from_url(settings.REDIS_URL)
    tg = get_telegram_service()
    try:
        for name, ping in ENGINES.items():
            key = f"investment_ai:engine_health:{name}"
            prev_raw = await r.get(key)
            prev = prev_raw.decode() if prev_raw else None
            try:
                result = await _asyncio.wait_for(ping(), timeout=60)
                if result is None:
                    continue  # engine not configured — nothing to watch
                state, err = "up", ""
            except Exception as exc:
                state, err = "down", str(exc)[:200]

            await r.set(key, state, ex=7 * 24 * 3600)

            if state == "down" and prev != "down":
                await tg.send_admin_alert(
                    f"🔴 <b>מנוע AI נפל: {name}</b>\n\n"
                    f"שגיאה: <code>{err}</code>\n\n"
                    f"<b>אבחון:</b> {_diagnose(err)}\n\n"
                    f"המערכת ממשיכה לעבוד עם שאר המנועים, אבל איכות הניתוח נפגעת "
                    f"עד שהמנוע יחזור."
                )
                logger.warning(f"[engine_health] {name} DOWN: {err}")
            elif state == "up" and prev == "down":
                await tg.send_admin_alert(f"🟢 <b>מנוע AI התאושש: {name}</b>\n\nחזר לפעול תקין.")
                logger.info(f"[engine_health] {name} recovered")
    except Exception as exc:
        logger.error(f"[engine_health] check failed: {exc}")
    finally:
        await r.aclose()


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

    # Personal Telegram linking — poll the bot for /start codes
    scheduler.add_job(
        job_poll_telegram_links,
        "interval",
        seconds=30,
        id="scheduled_telegram_link_poll",
        replace_existing=True,
    )

    # AI engine health check — every 6h, admin alert on down/recovery
    scheduler.add_job(
        job_engine_health_check,
        "interval",
        hours=6,
        id="scheduled_engine_health",
        replace_existing=True,
    )

    return scheduler


# Every job id the CURRENT code registers. Anything else found in the
# PostgreSQL job store is a leftover from an older code version — the store
# survives deploys, so renamed/removed jobs keep firing forever otherwise
# (a stale daily-09:00 full scan haunted us exactly this way).
KNOWN_JOB_IDS = {
    "scheduled_load_universe",
    "scheduled_prescreener",
    "scheduled_weekly_full_scan",
    "scheduled_earnings_watcher",
    "scheduled_ta_scan",
    "scheduled_news_watcher",
    "scheduled_quarterly_scan_batch",
    "scheduled_digest_sender",
    "scheduled_track_outcomes",
    "scheduled_price_alerts",
    "scheduled_portfolio_snapshot",
    "scheduled_telegram_link_poll",
    "scheduled_engine_health",
}


def remove_stale_jobs(scheduler: AsyncIOScheduler) -> list[str]:
    """Purge job-store entries that the current code no longer defines.
    Call right after scheduler.start(). Returns the removed job ids."""
    removed: list[str] = []
    try:
        for job in scheduler.get_jobs():
            if job.id not in KNOWN_JOB_IDS:
                scheduler.remove_job(job.id)
                removed.append(job.id)
                logger.warning(f"[scheduler] removed STALE job from store: {job.id} (trigger={job.trigger})")
    except Exception as exc:
        logger.error(f"[scheduler] stale-job cleanup failed: {exc}")
    return removed


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

    live = [
        RecommendationStatus.APPROVED,
        RecommendationStatus.PRESENTED_TO_USER,
        RecommendationStatus.ACTIONED,
    ]
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


async def restore_actioned_recommendations() -> int:
    """
    One-shot repair (startup): the old UI auto-dismissed a recommendation the
    moment the user recorded a BUY on it — hiding the analysis for a stock
    they now hold. Restore such recs to ACTIONED so they reappear in the feed.
    Identified precisely: DISMISSED recs referenced by an EXECUTED BUY order.
    """
    from sqlalchemy import select, update
    from app.core.database import AsyncSessionLocal
    from app.db.models.recommendation import Recommendation, RecommendationStatus
    from app.db.models.order import Order, OrderType, OrderStatus

    try:
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(Order.recommendation_id).where(
                    Order.recommendation_id.is_not(None),
                    Order.order_type == OrderType.BUY,
                    Order.status == OrderStatus.EXECUTED,
                ).distinct()
            )
            rec_ids = [r[0] for r in rows.all()]
            if not rec_ids:
                return 0
            result = await db.execute(
                update(Recommendation)
                .where(
                    Recommendation.id.in_(rec_ids),
                    Recommendation.status == RecommendationStatus.DISMISSED,
                )
                .values(status=RecommendationStatus.ACTIONED)
            )
            await db.commit()
            restored = result.rowcount or 0
            if restored:
                logger.info(f"[maintenance] restored {restored} bought-then-hidden recommendations to ACTIONED")
            return restored
    except Exception as exc:
        logger.error(f"[maintenance] restore_actioned failed: {exc}")
        return 0


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
