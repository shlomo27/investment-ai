"""
News Watcher — two-tier notification flow for master list stocks.

Every 30 minutes:
  1. Fetch new articles/tweets for each of the 50 master list stocks
  2. If new content found for a symbol:
     Tier 1  → notify watchers: "⚠️ AAPL mentioned on Bloomberg — checking impact..."
     TA run  → run_technical_workflow(symbol) to get current signal
     Tier 2  → notify watchers: "📊 AAPL: trend change WAIT → BUY_NOW"  (if notable)

Users only receive alerts for symbols they have in their watchlist
with alert_on_technical_signal = True.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


async def _run_news_watch() -> dict:
    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.db.models.asset import Asset
    from app.db.models.master_list import MasterListEntry
    from app.db.models.notification import NotificationType
    from app.db.models.user import User
    from app.db.models.watchlist import Watchlist
    from app.services.news.news_scanner import get_new_articles
    from app.services.notifications.service import NotificationService
    from sqlalchemy import select
    import redis.asyncio as aioredis

    redis_client = aioredis.from_url(settings.REDIS_URL)
    notifier = NotificationService()
    bearer = getattr(settings, "TWITTER_BEARER_TOKEN", "")

    # ── 1. Active master list symbols ────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(MasterListEntry.symbol)
            .where(MasterListEntry.is_active == True)
            .distinct()
        )
        symbols = [r[0] for r in rows.all()]

    if not symbols:
        logger.info("[news_watcher] No active master list symbols — skipping")
        return {"symbols_checked": 0}

    logger.info(f"[news_watcher] Watching {len(symbols)} master list symbols")
    symbols_with_news = 0
    total_articles = 0

    for symbol in symbols:
        try:
            # ── 2. New articles? ─────────────────────────────────────────────
            new_articles = await get_new_articles(symbol, redis_client, bearer)
            if not new_articles:
                continue

            symbols_with_news += 1
            total_articles += len(new_articles)
            sources = list({a["source"] for a in new_articles})
            sources_str = ", ".join(sources[:3])
            top_title = new_articles[0]["title"][:120]

            logger.info(f"[news_watcher] {symbol}: {len(new_articles)} new article(s) from {sources_str}")

            # ── 3. Who's watching this symbol? ───────────────────────────────
            async with AsyncSessionLocal() as db:
                watcher_rows = await db.execute(
                    select(Watchlist.user_id)
                    .where(Watchlist.symbol == symbol)
                    .where(Watchlist.alert_on_technical_signal == True)
                )
                watcher_ids = [r[0] for r in watcher_rows.all()]

            if not watcher_ids:
                continue

            # ── 4. Tier 1: news mention alert ────────────────────────────────
            for uid in watcher_ids:
                async with AsyncSessionLocal() as db:
                    u = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
                    if not u or not u.is_active:
                        continue
                    is_he = u.preferred_language == "he"
                    title_t1 = (
                        f"⚠️ {symbol} הוזכרה ב-{sources_str} — בודק השפעה..."
                        if is_he else
                        f"⚠️ {symbol} mentioned on {sources_str} — checking impact..."
                    )
                    await notifier.send_notification(
                        user_id=uid,
                        recommendation_id=None,
                        internal_detail={
                            "type": "NEWS_MENTION",
                            "symbol": symbol,
                            "sources": sources,
                            "article_count": len(new_articles),
                            "top_title": top_title,
                            "articles": [
                                {"title": a["title"], "source": a["source"], "url": a["url"]}
                                for a in new_articles[:3]
                            ],
                        },
                        db=db,
                        notification_type=NotificationType.ALERT,
                        title=title_t1,
                    )

            # ── 5. Technical analysis ─────────────────────────────────────────
            try:
                from app.agents.workflow import run_technical_workflow

                async with AsyncSessionLocal() as db:
                    asset = (
                        await db.execute(select(Asset).where(Asset.symbol == symbol))
                    ).scalar_one_or_none()
                exchange = asset.exchange.value if asset else "NASDAQ"

                ta_result = await run_technical_workflow(symbol=symbol, exchange=exchange)
                tech = ta_result.get("technical_analysis") or {}
                new_signal = tech.get("timing_signal", "WAIT")
                score = tech.get("technical_score", 0)
                reasoning = tech.get("signal_reasoning", "")

                # Compare with previous signal stored in Redis
                sig_key = f"investment_ai:last_signal:{symbol}"
                prev_bytes = await redis_client.get(sig_key)
                prev_signal = prev_bytes.decode() if prev_bytes else None
                signal_changed = prev_signal is not None and prev_signal != new_signal

                await redis_client.set(sig_key, new_signal, ex=86400 * 7)

                notable = new_signal in ("STRONG_BUY", "BUY_NOW", "SELL_NOW", "STRONG_SELL")

                # ── 6. Tier 2: TA result alert (only if notable or changed) ──
                if signal_changed or notable:
                    for uid in watcher_ids:
                        async with AsyncSessionLocal() as db:
                            u = (
                                await db.execute(select(User).where(User.id == uid))
                            ).scalar_one_or_none()
                            if not u or not u.is_active:
                                continue
                            is_he = u.preferred_language == "he"

                            if signal_changed:
                                title_t2 = (
                                    f"📊 {symbol}: שינוי מגמה! {prev_signal} → {new_signal}"
                                    if is_he else
                                    f"📊 {symbol}: Trend change! {prev_signal} → {new_signal}"
                                )
                            else:
                                title_t2 = (
                                    f"📊 {symbol}: סיגנל חזק — {new_signal}"
                                    if is_he else
                                    f"📊 {symbol}: Strong signal — {new_signal}"
                                )

                            await notifier.send_notification(
                                user_id=uid,
                                recommendation_id=None,
                                internal_detail={
                                    "type": "TECHNICAL_SIGNAL_UPDATE",
                                    "symbol": symbol,
                                    "signal": new_signal,
                                    "previous_signal": prev_signal,
                                    "signal_changed": signal_changed,
                                    "technical_score": score,
                                    "signal_reasoning": reasoning,
                                    "triggered_by": "news_mention",
                                },
                                db=db,
                                notification_type=NotificationType.ALERT,
                                title=title_t2,
                            )

            except Exception as ta_exc:
                logger.warning(f"[news_watcher] TA failed for {symbol}: {ta_exc}")

        except Exception as sym_exc:
            logger.error(f"[news_watcher] Error for {symbol}: {sym_exc}")

        # Avoid hammering APIs — small pause between symbols
        await asyncio.sleep(1)

    await redis_client.aclose()

    result = {
        "symbols_checked": len(symbols),
        "symbols_with_news": symbols_with_news,
        "total_articles": total_articles,
    }
    logger.info(f"[news_watcher] Done: {result}")
    return result


async def job_watch_news():
    """APScheduler entry point — called every 30 minutes."""
    logger.info("[scheduler] news_watcher started")
    try:
        result = await _run_news_watch()
        logger.info(f"[scheduler] news_watcher done: {result}")
    except Exception as exc:
        logger.error(f"[scheduler] news_watcher failed: {exc}")


# ── Optional Celery task (if running Celery workers) ─────────────────────────
try:
    from app.workers.celery_app import celery_app

    @celery_app.task(name="watch_master_list_news", bind=True, max_retries=1)
    def watch_master_list_news_task(self):
        import asyncio
        try:
            return asyncio.run(_run_news_watch())
        except Exception as exc:
            logger.error(f"watch_master_list_news_task failed: {exc}")
            raise self.retry(exc=exc, countdown=300)

except Exception:
    pass
