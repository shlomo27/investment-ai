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
}}

חשוב: עומדות לרשותך כותרות בלבד (ללא גוף המאמר) — לעולם אל תכתוב שחסר לך תוכן או שנדרש לקרוא את המאמר. אם הכותרות עצמן אינן מכילות מידע מהותי (כותרות סקרנות/שגרה), כתוב בסיכום: "סיקור תקשורתי שגרתי — ללא אירוע מהותי חדש", וקבע action=WAIT ו-confidence=LOW."""
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
        return {"sentiment": "NEUTRAL", "action": "WAIT", "confidence": "LOW",
                "summary": "", "_llm_failed": True}


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

    from app.db.models.portfolio import Portfolio

    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(MasterListEntry.symbol).where(MasterListEntry.is_active==True).distinct()
        )
        master_symbols = {r[0] for r in rows.all()}
        # Held positions stay news-monitored even after the master list rotates
        held_rows = await db.execute(
            select(Portfolio.symbol).where(Portfolio.quantity > 0).distinct()
        )
        held_symbols = {r[0] for r in held_rows.all()}

    symbols = sorted(master_symbols | held_symbols)
    if not symbols:
        logger.info("[news_watcher] No active master list symbols — skipping")
        return {"symbols_checked": 0}

    logger.info(
        f"[news_watcher] Watching {len(symbols)} symbols "
        f"(master={len(master_symbols)}, held-only={len(held_symbols - master_symbols)})"
    )
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
            if analysis.get("_llm_failed"):
                # News engine is down — don't send a news alert that only looks
                # analyzed. The technical alert (local math) still fires on its
                # own; the client is never shown a degraded/misleading read.
                logger.info(f"[news_watcher] {symbol}: news engine down — skipping news alert")
                continue
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

            # Real-time X (Twitter) buzz via Grok — only fires here because news
            # already broke on this held stock, so the cost stays bounded. A
            # viral X moment can independently move price, so strong buzz can
            # raise an alert even when the news read was lukewarm.
            x_score, x_posts, x_summary = 0.0, 0, ""
            try:
                from app.services.market_data.sentiment_service import SentimentService
                x = await SentimentService()._get_grok_x_sentiment(symbol)
                x_score = float(x.get("score", 0.0) or 0.0)
                x_posts = int(x.get("count", 0) or 0)
                x_posts_list = x.get("posts") or []
                x_summary = x_posts_list[0].get("text", "") if x_posts_list else ""
            except Exception as x_exc:
                logger.debug(f"[news_watcher] Grok X failed for {symbol}: {x_exc}")

            strong_x = x_posts >= 15 and abs(x_score) >= 0.4
            x_flag = ""
            if strong_x:
                x_flag = " 🔥X" if x_score > 0 else " 🧊X"

            emoji, decision = _COMBINED.get((news_action, ta_signal), ("📊", "עקוב"))

            # When BOTH news and TA say WAIT there is no actionable direction —
            # "אין סיגנל ברור" is noise, never worth an alert (even with X buzz,
            # since we still have nothing directional to tell the holder).
            if news_action == "WAIT" and ta_signal == "WAIT":
                continue

            # Cooldown: don't re-alert the same symbol+decision within 4h, even
            # as fresh articles keep publishing. Prevents a stock that's "in the
            # news" from pinging holders every 30-min run.
            cd_key = f"investment_ai:news_alert:{symbol}"
            prev_decision = await redis_client.get(cd_key)
            if prev_decision and prev_decision.decode() == decision:
                continue
            await redis_client.set(cd_key, decision, ex=4 * 3600)

            sources_str = ", ".join(list({a["source"] for a in new_articles})[:3])
            title  = f"{emoji} {symbol}: {decision} | {sources_str}{x_flag}"
            detail = {
                "type":            "NEWS_PLUS_TA",
                "symbol":          symbol,
                "news_sentiment":  sentiment,
                "news_action":     news_action,
                "news_summary":    summary,
                "news_confidence": confidence,
                "ta_signal":       ta_signal,
                "ta_score":        ta_score,
                "x_buzz_score":    round(x_score, 3),
                "x_buzz_posts":    x_posts,
                "x_buzz_summary":  x_summary,
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

    # ── Standalone social-buzz pass ──────────────────────────────────────────
    # A viral X moment can move a stock BEFORE any news breaks. Independently of
    # the news loop above, check X buzz for stocks users actually hold/watch and
    # alert on a strong spike. Scoped to held+watchlist to bound Grok cost.
    buzz_alerts = 0
    try:
        buzz_alerts = await _social_buzz_pass(redis_client, notifier)
    except Exception as e:
        logger.warning(f"[news_watcher] social-buzz pass failed: {e}")

    await redis_client.aclose()
    return {"symbols_checked": len(symbols), "symbols_alerted": symbols_alerted,
            "buzz_alerts": buzz_alerts}


async def _social_buzz_pass(redis_client, notifier) -> int:
    """Alert holders/watchlisters on a STRONG, FRESH X buzz spike — even with
    no news. Strong = >=15 posts AND |sentiment| >= 0.4. A per-symbol 4h
    cooldown plus a spike check (buzz notably higher than last seen) keeps it
    from firing on persistent chatter."""
    from app.core.database import AsyncSessionLocal
    from app.db.models.portfolio import Portfolio
    from app.db.models.watchlist import Watchlist
    from app.db.models.notification import NotificationType
    from app.services.market_data.sentiment_service import SentimentService
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        held = await db.execute(
            select(Portfolio.symbol).where(Portfolio.quantity > 0).distinct()
        )
        watched = await db.execute(
            select(Watchlist.symbol).where(Watchlist.alert_on_technical_signal == True).distinct()
        )
        symbols = sorted({r[0] for r in held.all()} | {r[0] for r in watched.all()})

    if not symbols:
        return 0

    alerts = 0
    svc = SentimentService()
    for symbol in symbols:
        if symbol.endswith(".TA"):
            continue  # Grok X search is US-focused
        try:
            x = await svc._get_grok_x_sentiment(symbol)
            posts = int(x.get("count", 0) or 0)
            score = float(x.get("score", 0.0) or 0.0)
            if posts < 15 or abs(score) < 0.4:
                continue  # not a strong buzz

            # Spike + cooldown: only alert if this run's post count is a clear
            # jump over the last seen, and not within the 4h cooldown.
            last_key = f"investment_ai:buzz_last:{symbol}"
            cd_key = f"investment_ai:buzz_alert:{symbol}"
            last_raw = await redis_client.get(last_key)
            last_posts = int(last_raw) if last_raw else 0
            await redis_client.set(last_key, posts, ex=24 * 3600)
            if await redis_client.get(cd_key):
                continue
            if last_posts and posts < last_posts * 1.5:
                continue  # buzz didn't meaningfully grow — not a fresh spike
            await redis_client.set(cd_key, "1", ex=4 * 3600)

            # Recipients
            async with AsyncSessionLocal() as db:
                hp = await db.execute(
                    select(Portfolio.user_id).where(Portfolio.symbol == symbol, Portfolio.quantity > 0).distinct()
                )
                wp = await db.execute(
                    select(Watchlist.user_id).where(
                        Watchlist.symbol == symbol, Watchlist.alert_on_technical_signal == True
                    ).distinct()
                )
                user_ids = list({r[0] for r in hp.all()} | {r[0] for r in wp.all()})
            if not user_ids:
                continue

            mood = "חיובי 🔥" if score > 0 else "שלילי 🧊"
            sample = ""
            posts_list = x.get("posts") or []
            if posts_list:
                sample = " | דוגמה: " + (posts_list[0].get("text", "") or "")[:120]
            title = (f"📣 {symbol}: באזz חריג ב-X — {posts} פוסטים, סנטימנט {mood} ({score:+.2f}). "
                     f"ייתכן שהמניה תזוז לפני שיגיעו חדשות.{sample} 👈 בדוק במערכת.")
            async with AsyncSessionLocal() as db:
                for uid in user_ids:
                    await notifier.send_notification(
                        user_id=uid, recommendation_id=None,
                        internal_detail={"symbol": symbol, "signal": "X_BUZZ",
                                         "x_buzz_posts": posts, "x_buzz_score": round(score, 3),
                                         "trigger": "SOCIAL_BUZZ"},
                        db=db, notification_type=NotificationType.ALERT, title=title,
                    )
            alerts += 1
            logger.info(f"[news_watcher] social-buzz alert {symbol}: {posts} posts, score {score:.2f} → {len(user_ids)} users")
        except Exception as e:
            logger.debug(f"[news_watcher] buzz check {symbol} failed: {e}")
        await asyncio.sleep(1)
    return alerts


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
