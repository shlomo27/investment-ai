"""
News Watcher — two-tier alert flow for master list stocks.

Every 30 minutes:
  1. Fetch new articles/tweets for each of the 50 master list stocks
     Sources: Yahoo Finance (free), Google News RSS (free), Twitter/X (optional key)
  2. Analyze news content with Claude Haiku (sentiment + action + Hebrew summary)
  3. Run TA on the symbol → get timing_signal
  4. Combine news sentiment + TA signal → ONE actionable alert to:
     - Users who HOLD the stock in their portfolio (quantity > 0)
     - Users who have it on their watchlist with alert_on_technical_signal=True
"""
import asyncio
import json
import logging

logger = logging.getLogger(__name__)

_COMBINED = {
    ("BUY",  "STRONG_BUY"):  ("🚀", "קנה חזק"),
    ("BUY",  "BUY_NOW"):     ("📈", "קנה"),
    ("BUY",  "WAIT"):        ("📈", "נטייה לקנות — עקוב"),
    ("BUY",  "SELL_NOW"):    ("⚡", "סיגנלים מעורבים — בחן"),
    ("BUY",  "STRONG_SELL"): ("⚡", "סיגנלים מנוגדים — בחן"),
    ("SELL", "STRONG_SELL"): ("🔴", "מכור חזק"),
    ("SELL", "SELL_NOW"):    ("⚠️", "שקול למכור"),
    ("SELL", "WAIT"):        ("⚠️", "חדשות שליליות — עקוב"),
    ("SELL", "BUY_NOW"):     ("⚡", "סיגנלים מנוגדים — בחן"),
    ("SELL", "STRONG_BUY"):  ("⚡", "סיגנלים מנוגדים — בחן"),
    ("WAIT", "STRONG_BUY"):  ("📈", "קנה חזק (TA)"),
    ("WAIT", "BUY_NOW"):     ("📈", "קנה (TA)"),
    ("WAIT", "SELL_NOW"):    ("⚠️", "שקול למכור (TA)"),
    ("WAIT", "STRONG_SELL"): ("🔴", "מכור חזק (TA)"),
    ("WAIT", "WAIT"):        ("😴", "המתן — אין סיגנל ברור"),
}


async def _analyze_news_with_llm(symbol: str, articles: list) -> dict:
    """Claude Haiku analysis — ~$0.001/call. Falls back to NEUTRAL/WAIT/LOW on error."""
    from app.core.config import settings
    from anthropic import AsyncAnthropic

    titles = "\n".join(f"- [{a['source']}] {a['title']}" for a in articles[:5])
    prompt = f"""אתה אנליסט השקעות. קיבלת את הידיעות הבאות לגבי המניה {symbol}:

{titles}

נתח את ההשפעה על המניה וענה בפורמט JSON בלבד (ללא טקסט נוסף):
{{
  "sentiment": "POSITIVE" | "NEGATIVE" | "NEUTRAL",
  "action": "BUY" | "SELL" | "WAIT",
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "summary": "משפט אחד קצר בעברית שמסכם מה המשמעות עבור המשקיע"
}}"""
    try:
        client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as e:
        logger.debug(f"[news_watcher] LLM failed for {symbol}: {e}")
        return {"sentiment": "NEUTRAL", "action": "WAIT", "confidence": "LOW", "summary": ""}


async def _get_recipient_ids(symbol: str) -> list:
    """Union of portfolio holders (qty>0) and watchlist alert users."""
    from app.core.database import AsyncSessionLocal
    from app.db.models.portfolio import Portfolio
    from app.db.models.watchlist import Watchlist
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        pf = await db.execute(
            select(Portfolio.user_id).where(Portfolio.symbol==symbol, Portfolio.quantity>0).distinct()
        )
        wl = await db.execute(
            select(Watchlist.user_id).where(
                Watchlist.symbol==symbol, Watchlist.alert_on_technical_signal==True
            ).distinct()
        )
        return list({r[0] for r in pf.all()} | {r[0] for r in wl.all()})


async def _run_news_watch() -> dict:
    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.db.models.asset import Asset
    from app.db.models.master_list import MasterListEntry
    from app.db.models.notification import NotificationType
    from app.services.news.news_scanner import get_new_articles
    from app.services.notifications.service import NotificationService
    from sqlalchemy import select
    import redis.asyncio as aioredis

    redis_client = aioredis.from_url(settings.REDIS_URL)
    notifier = NotificationService()
    bearer = getattr(settings, "TWITTER_BEARER_TOKEN", "")

    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(MasterListEntry.symbol).where(MasterListEntry.is_active==True).distinct()
        )
        symbols = [r[0] for r in rows.all()]

    if not symbols:
        logger.info("[news_watcher] No active master list symbols — skipping")
        return {"symbols_checked": 0}

    logger.info(f"[news_watcher] Watching {len(symbols)} symbols")
    symbols_alerted = 0

    for symbol in symbols:
        try:
            new_articles = await get_new_articles(symbol, redis_client, bearer)
            if not new_articles:
                continue

            recipient_ids = await _get_recipient_ids(symbol)
            if not recipient_ids:
                continue

            analysis    = await _analyze_news_with_llm(symbol, new_articles)
            news_action = analysis.get("action", "WAIT")
            sentiment   = analysis.get("sentiment", "NEUTRAL")
            summary     = analysis.get("summary", "")
            confidence  = analysis.get("confidence", "LOW")

            ta_signal, ta_score = "WAIT", 50
            try:
                from app.agents.workflow import run_technical_workflow
                async with AsyncSessionLocal() as db:
                    asset = (await db.execute(select(Asset).where(Asset.symbol==symbol))).scalar_one_or_none()
                exchange = asset.exchange.value if asset else "NASDAQ"
                ta_result = await run_technical_workflow(symbol=symbol, exchange=exchange)
                tech      = ta_result.get("technical_analysis") or {}
                ta_signal = tech.get("timing_signal", "WAIT")
                ta_score  = tech.get("technical_score", 50)
            except Exception as ta_exc:
                logger.warning(f"[news_watcher] TA failed for {symbol}: {ta_exc}")

            emoji, decision = _COMBINED.get((news_action, ta_signal), ("📊", "עקוב"))

            if news_action == "WAIT" and ta_signal == "WAIT" and confidence == "LOW":
                continue

            sources_str = ", ".join(list({a["source"] for a in new_articles})[:3])
            title  = f"{emoji} {symbol}: {decision} | {sources_str}"
            detail = {
                "type":            "NEWS_PLUS_TA",
                "symbol":          symbol,
                "news_sentiment":  sentiment,
                "news_action":     news_action,
                "news_summary":    summary,
                "news_confidence": confidence,
                "ta_signal":       ta_signal,
                "ta_score":        ta_score,
                "combined":        decision,
                "sources":         list({a["source"] for a in new_articles}),
                "articles":        [{"title": a["title"], "source": a["source"], "url": a.get("url","")} for a in new_articles[:3]],
            }

            async with AsyncSessionLocal() as db:
                for uid in recipient_ids:
                    await notifier.send_notification(
                        user_id=uid, recommendation_id=None, internal_detail=detail,
                        db=db, notification_type=NotificationType.ALERT, title=title,
                    )

            symbols_alerted += 1
            logger.info(f"[news_watcher] {symbol}: '{decision}' → {len(recipient_ids)} users")

        except Exception as sym_exc:
            logger.error(f"[news_watcher] {symbol}: {sym_exc}")
        await asyncio.sleep(1)

    await redis_client.aclose()
    return {"symbols_checked": len(symbols), "symbols_alerted": symbols_alerted}


async def job_watch_news():
    """APScheduler entry point — called every 30 minutes."""
    logger.info("[scheduler] news_watcher started")
    try:
        result = await _run_news_watch()
        logger.info(f"[scheduler] news_watcher done: {result}")
    except Exception as exc:
        logger.error(f"[scheduler] news_watcher failed: {exc}")


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
