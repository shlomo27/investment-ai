"""
Pre-Screener
Daily Celery task (08:00 IL / 05:00 UTC) that scores all universe stocks
using yfinance metrics only (no AI cost) and activates the top candidates
for full AI analysis via is_active_in_pool.

Scoring logic:
  LONG score (0-100):  undervalued + positive momentum + quality
  SHORT score (0-100): overvalued + negative momentum + deteriorating quality

Activation:
  Top LONG_SLOTS stocks  → direction_bias=LONG,  is_active_in_pool=True
  Top SHORT_SLOTS stocks → direction_bias=SHORT, is_active_in_pool=True
  Rest → is_active_in_pool=False (but stay in universe)
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import yfinance as yf
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.db.models.asset import Asset
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

LONG_SLOTS = 80   # top LONG candidates to activate  (~9-day cycle for S&P500+400)
SHORT_SLOTS = 20  # top SHORT candidates to activate
BATCH_SIZE = 50   # symbols per yfinance download batch


def _score_ticker(info: dict) -> tuple[float, float]:
    """
    Compute (long_score, short_score) from yfinance .info dict.
    Both scores are 0-100. Higher = stronger signal.
    """
    long_pts = 0.0
    short_pts = 0.0

    # ── Valuation ────────────────────────────────────────────────────────────
    pe = info.get("trailingPE") or info.get("forwardPE")
    if pe:
        if pe < 15:
            long_pts += 20
        elif pe < 25:
            long_pts += 10
        elif pe > 40:
            short_pts += 20
        elif pe > 30:
            short_pts += 10

    pb = info.get("priceToBook")
    if pb:
        if pb < 1.5:
            long_pts += 15
        elif pb < 3:
            long_pts += 5
        elif pb > 8:
            short_pts += 15
        elif pb > 5:
            short_pts += 8

    # ── Momentum / Price trend ────────────────────────────────────────────────
    week52_high = info.get("fiftyTwoWeekHigh")
    week52_low = info.get("fiftyTwoWeekLow")
    current = info.get("currentPrice") or info.get("regularMarketPrice")

    if week52_high and week52_low and current:
        rng = week52_high - week52_low
        if rng > 0:
            pos = (current - week52_low) / rng  # 0 = at low, 1 = at high
            if pos < 0.25:
                long_pts += 15  # near 52w low — potential reversal
            elif pos > 0.85:
                short_pts += 10  # near 52w high — stretched

    # ── Earnings / Revenue growth ─────────────────────────────────────────────
    earnings_growth = info.get("earningsQuarterlyGrowth")
    rev_growth = info.get("revenueGrowth")

    if earnings_growth is not None:
        if earnings_growth > 0.20:
            long_pts += 15
        elif earnings_growth > 0:
            long_pts += 5
        elif earnings_growth < -0.20:
            short_pts += 15
        elif earnings_growth < 0:
            short_pts += 5

    if rev_growth is not None:
        if rev_growth > 0.15:
            long_pts += 10
        elif rev_growth < -0.10:
            short_pts += 10

    # ── Analyst sentiment ─────────────────────────────────────────────────────
    rec_mean = info.get("recommendationMean")  # 1=Strong Buy, 5=Sell
    if rec_mean:
        if rec_mean <= 2.0:
            long_pts += 15
        elif rec_mean <= 2.5:
            long_pts += 8
        elif rec_mean >= 4.0:
            short_pts += 15
        elif rec_mean >= 3.5:
            short_pts += 8

    # ── Short interest ────────────────────────────────────────────────────────
    short_pct = info.get("shortPercentOfFloat")
    if short_pct:
        if short_pct > 0.20:
            short_pts += 10  # heavily shorted — momentum short
        elif short_pct < 0.02:
            long_pts += 5   # very low short interest — confidence

    return min(long_pts, 100.0), min(short_pts, 100.0)


def _recency_adjustment(last_analyzed_at: Optional[datetime]) -> float:
    """
    Return a score ADDITION (positive = bonus, negative = penalty) based on
    how recently this stock was analyzed.

    Critical for Railway deployment where yfinance.info is often blocked and
    most stocks end up with score=0.  Without this, the same first-N stocks
    in the list win every day.  With positive bonuses for stale/never-analyzed
    stocks, the screener cycles through all S&P500/400 stocks over time even
    when fundamental data can't be fetched.
    """
    if last_analyzed_at is None:
        return 30.0   # never analyzed → highest priority
    now = datetime.now(timezone.utc)
    if last_analyzed_at.tzinfo is None:
        last_analyzed_at = last_analyzed_at.replace(tzinfo=timezone.utc)
    days = (now - last_analyzed_at).total_seconds() / 86400
    if days >= 7:
        return 20.0   # stale (≥7 days): strong bonus
    if days >= 3:
        return 10.0   # semi-stale (3-7 days): moderate bonus
    if days >= 1:
        return 3.0    # analyzed 1-3 days ago: tiny bonus
    return -30.0      # analyzed today: strong penalty → rotate out


def _batch_symbols(symbols: list[str]) -> list[list[str]]:
    return [symbols[i:i + BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)]


async def run_pre_screener(db: AsyncSession) -> dict:
    """
    Score all in-universe assets and activate top LONG/SHORT candidates.
    Returns summary dict.
    """
    result = await db.execute(
        select(Asset.id, Asset.symbol, Asset.last_analyzed_at).where(Asset.in_universe == True)
    )
    universe = result.fetchall()  # [(id, symbol, last_analyzed_at), ...]

    if not universe:
        logger.warning("Pre-screener: no universe stocks found")
        return {"scored": 0, "long_activated": 0, "short_activated": 0}

    symbol_to_id = {sym: aid for aid, sym, _ in universe}
    symbol_to_analyzed: dict[str, Optional[datetime]] = {sym: ts for _, sym, ts in universe}
    symbols = list(symbol_to_id.keys())
    logger.info(f"Pre-screener: scoring {len(symbols)} universe stocks")

    scores: dict[str, tuple[float, float]] = {}

    for batch in _batch_symbols(symbols):
        # Fetch yfinance data — failures just mean empty info dicts
        batch_info: dict[str, dict] = {}
        try:
            tickers = yf.Tickers(" ".join(batch))
            for sym in batch:
                try:
                    batch_info[sym] = tickers.tickers[sym].info or {}
                except Exception as e:
                    logger.debug(f"yfinance info failed for {sym}: {e}")
                    batch_info[sym] = {}
        except Exception as e:
            logger.error(f"yfinance batch fetch failed: {e}")
            for sym in batch:
                batch_info[sym] = {}

        # Score each symbol — recency adjustment ALWAYS applied regardless of
        # whether yfinance returned data (critical on Railway where .info is blocked)
        for sym in batch:
            long_s, short_s = _score_ticker(batch_info.get(sym, {}))
            adj = _recency_adjustment(symbol_to_analyzed.get(sym))
            scores[sym] = (max(0.0, long_s + adj), max(0.0, short_s + adj))

    # Sort by score to pick top candidates
    long_ranked = sorted(scores.items(), key=lambda x: x[1][0], reverse=True)
    short_ranked = sorted(scores.items(), key=lambda x: x[1][1], reverse=True)

    long_top = {sym for sym, _ in long_ranked[:LONG_SLOTS]}
    # SHORT candidates are picked from stocks NOT already selected as LONG.
    # Without this, when all scores are tied, short_ranked[:SHORT_SLOTS] returns
    # the same symbols as long_ranked[:SHORT_SLOTS] (all in long_top) → 0 shorts.
    short_candidates = [sym for sym, _ in short_ranked if sym not in long_top]
    short_top = set(short_candidates[:SHORT_SLOTS])

    now = datetime.now(timezone.utc)

    # Deactivate all universe stocks first
    await db.execute(
        update(Asset)
        .where(Asset.in_universe == True)
        .values(is_active_in_pool=False, direction_bias="NEUTRAL")
    )

    # Activate LONG candidates
    long_activated = 0
    for sym in long_top:
        long_s, short_s = scores[sym]
        await db.execute(
            update(Asset)
            .where(Asset.symbol == sym)
            .values(
                is_active_in_pool=True,
                direction_bias="LONG",
                long_score=long_s,
                short_score=short_s,
                screener_activated_at=now,
            )
        )
        long_activated += 1

    # Activate SHORT candidates
    short_activated = 0
    for sym in short_top:
        long_s, short_s = scores[sym]
        await db.execute(
            update(Asset)
            .where(Asset.symbol == sym)
            .values(
                is_active_in_pool=True,
                direction_bias="SHORT",
                long_score=long_s,
                short_score=short_s,
                screener_activated_at=now,
            )
        )
        short_activated += 1

    # Persist scores for non-activated stocks too (for UI inspection)
    for sym, (long_s, short_s) in scores.items():
        if sym not in long_top and sym not in short_top:
            await db.execute(
                update(Asset)
                .where(Asset.symbol == sym)
                .values(long_score=long_s, short_score=short_s)
            )

    await db.flush()

    logger.info(
        f"Pre-screener complete: scored={len(scores)}, "
        f"long_activated={long_activated}, short_activated={short_activated}"
    )
    return {
        "scored": len(scores),
        "long_activated": long_activated,
        "short_activated": short_activated,
        "top_long": [sym for sym, _ in long_ranked[:5]],
        "top_short": [sym for sym, _ in short_ranked[:5]],
    }


@celery_app.task(name="run_pre_screener", bind=True, max_retries=1)
def run_pre_screener_task(self):
    """Daily pre-screener: scores universe and activates top LONG/SHORT candidates."""
    import asyncio

    async def _run():
        async with AsyncSessionLocal() as db:
            async with db.begin():
                return await run_pre_screener(db)

    try:
        result = asyncio.run(_run())
        logger.info(f"Pre-screener task done: {result}")
        return result
    except Exception as exc:
        logger.error(f"Pre-screener task failed: {exc}")
        raise self.retry(exc=exc, countdown=120)
