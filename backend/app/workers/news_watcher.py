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
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ─── Event-triggered X search ────────────────────────────────────────────────
# Asking Grok about every watched symbol every 30 minutes costs real money per
# search and almost always answers "nothing happening". Price and volume come
# free from Yahoo, and a post that genuinely moves a stock moves them too — so
# they decide when an X search is worth paying for. Pre/post-market bars are
# included, which is exactly when a tweet lands before the open.
MOVE_PCT_TRIGGER   = 3.0   # % move vs previous close
VOLUME_MULT_TRIGGER = 2.0  # recent volume vs its own normal
DAILY_FLOOR_HOURS  = 20    # every symbol still gets one check per ~day


def _fetch_movement(symbols: list[str]) -> dict:
    """One bulk Yahoo download for all symbols → {symbol: {move_pct, vol_mult}}.

    Free, one HTTP round trip regardless of symbol count. Returns {} on failure;
    the caller treats that as "no movement data" rather than as "check nothing",
    so a Yahoo outage can't silently turn the watcher into a spender again.
    """
    try:
        import yfinance as yf
        data = yf.download(
            symbols, period="5d", interval="1h", prepost=True,
            group_by="ticker", auto_adjust=False, progress=False, threads=False,
        )
    except Exception as e:
        logger.warning(f"[news_watcher] movement fetch failed: {e}")
        return {}

    out: dict = {}
    for sym in symbols:
        try:
            df = data[sym] if len(symbols) > 1 else data
            df = df.dropna(subset=["Close"])
            if len(df) < 8:
                continue
            closes = df["Close"]
            last = float(closes.iloc[-1])
            # Reference = close ~1 trading day back (7 hourly bars ≈ one session)
            ref = float(closes.iloc[-8])
            move_pct = ((last - ref) / ref * 100) if ref else 0.0

            vol_mult = 0.0
            if "Volume" in df.columns:
                vols = df["Volume"].dropna()
                if len(vols) >= 10:
                    recent = float(vols.iloc[-2:].mean())
                    normal = float(vols.iloc[:-2].median())
                    if normal > 0:
                        vol_mult = recent / normal
            out[sym] = {"move_pct": round(move_pct, 2), "vol_mult": round(vol_mult, 2)}
        except Exception:
            continue
    return out


async def _fetch_movement_alpaca(symbols: list[str]) -> dict:
    """Same shape as _fetch_movement, sourced from Alpaca daily bars.

    Alpaca answers reliably from cloud IPs where Yahoo does not, and serves
    hundreds of symbols per request.
    """
    try:
        from app.services.market_data.alpaca_service import get_alpaca_service
        bars = await get_alpaca_service().get_bars_multi(symbols, days=40)
    except Exception as e:
        logger.warning(f"[news_watcher] Alpaca movement fetch failed: {e}")
        return {}

    out: dict = {}
    for sym, rows in bars.items():
        if len(rows) < 5:
            continue
        closes = [r["close"] for r in rows if r.get("close")]
        vols = [r["volume"] for r in rows if r.get("volume") is not None]
        if len(closes) < 2:
            continue
        move = ((closes[-1] - closes[-2]) / closes[-2] * 100) if closes[-2] else 0.0
        vol_mult = 0.0
        if len(vols) >= 6:
            prior = sorted(vols[:-1])
            median = prior[len(prior) // 2]
            if median > 0:
                vol_mult = vols[-1] / median
        out[sym] = {"move_pct": round(move, 2), "vol_mult": round(vol_mult, 2)}
    if out:
        logger.info(f"[news_watcher] Alpaca supplied movement for {len(out)}/{len(symbols)} symbols")
    return out


async def _fetch_movement_fmp(symbols: list[str]) -> dict:
    """Same shape as _fetch_movement, sourced from FMP batch quotes.

    Used when Yahoo returns nothing. FMP gives today's move and volume against
    its own average directly, so no history maths is needed.
    """
    try:
        from app.services.market_data.fmp_service import get_fmp_service
        quotes = await get_fmp_service().get_batch_quotes(symbols)
    except Exception as e:
        logger.warning(f"[news_watcher] FMP movement fetch failed: {e}")
        return {}

    out: dict = {}
    for sym, q in quotes.items():
        vol, avg = q.get("volume") or 0, q.get("avg_volume") or 0
        out[sym] = {
            "move_pct": round(float(q.get("change_pct") or 0), 2),
            "vol_mult": round(vol / avg, 2) if avg > 0 else 0.0,
        }
    if out:
        logger.info(f"[news_watcher] FMP supplied movement for {len(out)}/{len(symbols)} symbols")
    return out


def _should_check_x(sym: str, movement: dict, last_checked_iso) -> tuple[bool, str]:
    """Decide whether this symbol earns a paid X search right now."""
    m = movement.get(sym)
    if m:
        if abs(m["move_pct"]) >= MOVE_PCT_TRIGGER:
            return True, f"תזוזת מחיר {m['move_pct']:+.1f}%"
        if m["vol_mult"] >= VOLUME_MULT_TRIGGER:
            return True, f"נפח מסחר ×{m['vol_mult']:.1f}"

    # Floor: never let a symbol go more than ~a day without any X read, so a
    # slow-building story isn't missed just because price hasn't moved yet.
    if not last_checked_iso:
        return True, "בדיקה יומית"
    try:
        last = datetime.fromisoformat(last_checked_iso)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - last).total_seconds() >= DAILY_FLOOR_HOURS * 3600:
            return True, "בדיקה יומית"
    except Exception:
        return True, "בדיקה יומית"
    return False, ""

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

    from app.db.models.recommendation import Recommendation, RecommendationStatus

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
        # Every stock with a LIVE recommendation, which is what clients
        # actually see. The master list is published by hand and goes stale
        # between publications, so keying news monitoring on it alone left a
        # freshly recommended stock with no news watch at all — the TA scan
        # already covers live recommendations; news did not.
        live_rows = await db.execute(
            select(Recommendation.symbol).where(
                Recommendation.status.in_([
                    RecommendationStatus.APPROVED,
                    RecommendationStatus.PRESENTED_TO_USER,
                    RecommendationStatus.ACTIONED,
                ])
            ).distinct()
        )
        live_symbols = {r[0] for r in live_rows.all()}

    symbols = sorted(master_symbols | held_symbols | live_symbols)
    if not symbols:
        logger.info("[news_watcher] nothing to watch — no master list, holdings or live recs")
        return {"symbols_checked": 0}

    logger.info(
        f"[news_watcher] Watching {len(symbols)} symbols (master={len(master_symbols)}, "
        f"held-only={len(held_symbols - master_symbols)}, "
        f"live-rec-only={len(live_symbols - master_symbols - held_symbols)})"
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

            # Publish the news read so the technical path can see it. The
            # entry-point alert announces that "both sides agree" from the
            # fundamental call and the technical signal alone, and had no way
            # to know the news watcher had just flagged the opposite — so a
            # stock could receive "conflicting signals, examine" and "both
            # sides agree" within the same minute. Stored on every run, alert
            # or not, since a negative read that is too weak to alert on is
            # exactly what must still temper a confident entry call.
            try:
                import json as _json
                await redis_client.set(
                    f"investment_ai:news_view:{symbol}",
                    _json.dumps({"action": news_action, "sentiment": sentiment,
                                 "summary": summary[:200]}),
                    ex=24 * 3600,
                )
            except Exception:
                pass

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

            # Alert on a CHANGE of direction, not on the passage of time.
            #
            # This was a four-hour cooldown, which meant the suppression simply
            # expired: GOOGL alerted "קנה" at 12:22 and again at 16:22, exactly
            # four hours later, with the same verdict and nothing new for the
            # holder to act on. A stock that stays in the news re-alerted every
            # four hours indefinitely. The direction turning positive is the
            # event worth a message; it staying positive is not.
            #
            # The key is held for a week so a persisting verdict stays quiet,
            # and any genuine flip still alerts on the very next run.
            cd_key = f"investment_ai:news_alert:{symbol}"
            prev_decision = await redis_client.get(cd_key)
            prev_decision = prev_decision.decode() if prev_decision else None

            # Exception: a fresh, strong X moment breaks the silence even when
            # the direction is unchanged. Something going viral can move a
            # price on its own, which is the whole reason Grok is consulted
            # here — and holding that back because the verdict happens to still
            # read "buy" would suppress the one thing the holder could not have
            # known already. Gated on its own key so a buzz that persists for
            # days does not restart the four-hourly pinging in a new costume:
            # the direction of the buzz must be new, or a day must have passed.
            x_break = False
            if strong_x:
                x_key = f"investment_ai:news_x_buzz:{symbol}"
                x_dir = "pos" if x_score > 0 else "neg"
                prev_x = await redis_client.get(x_key)
                if (prev_x.decode() if prev_x else None) != x_dir:
                    x_break = True
                    await redis_client.set(x_key, x_dir, ex=24 * 3600)

            if prev_decision == decision and not x_break:
                await redis_client.expire(cd_key, 7 * 24 * 3600)
                continue
            await redis_client.set(cd_key, decision, ex=7 * 24 * 3600)

            sources_str = ", ".join(list({a["source"] for a in new_articles})[:3])
            # Name the reason when the verdict itself did not change, so the
            # message cannot read as the repeat alert this gating exists to stop.
            reason = ""
            if x_break and prev_decision == decision:
                reason = (" — באז חריג ב-X" if x_score > 0 else " — באז שלילי חריג ב-X")
            title  = f"{emoji} {symbol}: {decision}{reason} | {sources_str}{x_flag}"
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

    # Grok keeps running — but flag abnormal daily volume once, so a runaway
    # loop surfaces as a message rather than as a surprise credit charge.
    try:
        from app.services.market_data.sentiment_service import (
            grok_calls_today, grok_volume_is_abnormal,
        )
        if await grok_volume_is_abnormal() and not await redis_client.get("investment_ai:grok_vol_alert"):
            await redis_client.set("investment_ai:grok_vol_alert", "1", ex=20 * 3600)
            from app.services.notifications.telegram_service import get_telegram_service
            used = await grok_calls_today()
            await get_telegram_service().send_admin_alert(
                f"📊 <b>שימוש חריג ב-Grok</b>\nבוצעו {used} חיפושי X בתשלום היום — "
                f"יותר מהצפוי. <b>המעקב ממשיך כרגיל ולא נחסם כלום.</b>\n"
                f"שווה לבדוק את מספר המניות במעקב ואת יתרת הקרדיטים ב-xAI."
            )
    except Exception as e:
        logger.debug(f"[news_watcher] grok volume check failed: {e}")

    await redis_client.aclose()
    return {"symbols_checked": len(symbols), "symbols_alerted": symbols_alerted,
            "buzz_alerts": buzz_alerts}


async def _social_buzz_pass(redis_client, notifier) -> int:
    """Alert holders/watchlisters on a STRONG, FRESH X buzz spike — even with
    no news. Strong = >=15 posts AND |sentiment| >= 0.4. A per-symbol 4h
    cooldown plus a spike check (buzz notably higher than last seen) keeps it
    from firing on persistent chatter.

    X is searched only for symbols whose price or volume actually moved (plus a
    once-a-day floor per symbol), because each search is billed and a post that
    moves a stock moves its tape too."""
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

    us_symbols = [s for s in symbols if not s.endswith(".TA")]
    if not us_symbols:
        return 0

    # One free bulk price/volume read for the whole list decides who is worth a
    # paid X search this cycle.
    movement = await asyncio.get_event_loop().run_in_executor(
        None, _fetch_movement, us_symbols
    )
    if not movement:
        # Yahoo blocks bulk requests from cloud IPs often enough that a single
        # source here is not good enough — one outage would blind the trigger.
        logger.warning("[news_watcher] Yahoo movement fetch empty — trying Alpaca")
        movement = await _fetch_movement_alpaca(us_symbols)
    if not movement:
        logger.warning("[news_watcher] Alpaca empty too — trying FMP batch quotes")
        movement = await _fetch_movement_fmp(us_symbols)
    if not movement:
        logger.warning(
            "[news_watcher] no movement data from any source — "
            "X search limited to the daily floor"
        )

    alerts = 0
    checked = 0
    svc = SentimentService()
    for symbol in us_symbols:
        try:
            last_key = f"investment_ai:buzz_last:{symbol}"
            cd_key = f"investment_ai:buzz_alert:{symbol}"
            seen_key = f"investment_ai:buzz_seen:{symbol}"
            # Check the cooldown BEFORE asking Grok. A symbol still inside its
            # 4h window cannot produce an alert whatever the answer is, so
            # paying for the search would buy nothing.
            if await redis_client.get(cd_key):
                continue

            last_checked = await redis_client.get(seen_key)
            if isinstance(last_checked, bytes):
                last_checked = last_checked.decode()
            do_check, reason = _should_check_x(symbol, movement, last_checked)
            if not do_check:
                continue

            checked += 1
            await redis_client.set(
                seen_key, datetime.now(timezone.utc).isoformat(), ex=3 * 24 * 3600
            )
            logger.info(f"[news_watcher] X search for {symbol} — {reason}")

            x = await svc._get_grok_x_sentiment(symbol)
            posts = int(x.get("count", 0) or 0)
            score = float(x.get("score", 0.0) or 0.0)
            if posts < 15 or abs(score) < 0.4:
                continue  # not a strong buzz

            # Spike check: only alert when this run's post count is a clear
            # jump over the last seen.
            last_raw = await redis_client.get(last_key)
            last_posts = int(last_raw) if last_raw else 0
            await redis_client.set(last_key, posts, ex=24 * 3600)
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
            direction = ("סנטימנט חיובי — ייתכן לחץ קנייה" if score > 0
                         else "סנטימנט שלילי — ייתכן לחץ מכירה")
            # Clean multi-line layout — Hebrew lines kept separate from the
            # English tweet sample so RTL doesn't scramble them.
            lines = [
                f"📣 {symbol}: באזz חריג ברשת X",
                f"פעילות חריגה: {posts} פוסטים · {mood} ({score:+.2f})",
                f"מה הפעיל את הבדיקה: {reason}",
                f"{direction}. פעמים רבות התנועה בטוויטר מקדימה את החדשות.",
            ]
            posts_list = x.get("posts") or []
            if posts_list and posts_list[0].get("text"):
                lines.append("📝 ציטוט לדוגמה:")
                lines.append((posts_list[0]["text"] or "")[:160])
            lines.append("👈 פתח את המניה במערכת לניתוח הטכני והחדשות המלאים.")
            title = "\n".join(lines)
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
    logger.info(
        f"[news_watcher] buzz pass: {checked}/{len(us_symbols)} symbols warranted "
        f"a paid X search, {alerts} alerts"
    )
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
