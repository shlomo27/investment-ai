"""
Pre-Screener
Scores all universe stocks and activates the top candidates for full AI analysis.

Scoring:
  Base score = stored long_score / short_score from previous analyses (0-100).
  Recency adjustment = bonus for never/rarely analyzed stocks, penalty for today.

  On Railway, yfinance .info is blocked — all base scores start at 0.
  The recency adjustment is therefore the primary driver of stock selection,
  which is exactly what we want: rotate through all ~900 S&P500+400 stocks
  evenly over time (~9 day cycle for 100 stocks/day).

Activation:
  Top LONG_SLOTS stocks  → direction_bias=LONG,  is_active_in_pool=True
  Top SHORT_SLOTS stocks → direction_bias=SHORT, is_active_in_pool=True
  Rest → is_active_in_pool=False (stay in universe for future cycles)
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.db.models.asset import Asset
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

LONG_SLOTS = 80   # LONG candidates per day  → 80 × 9 days ≈ 720 (S&P500)
SHORT_SLOTS = 20  # SHORT candidates per day → 20 × 9 days ≈ 180 (S&P400 tail)


def _recency_adjustment(last_analyzed_at: Optional[datetime]) -> float:
    """
    Score bonus/penalty based on how recently this stock was AI-analyzed.
    This drives rotation: never-analyzed stocks are always picked first.
    """
    if last_analyzed_at is None:
        return 30.0   # never analyzed → top priority
    now = datetime.now(timezone.utc)
    if last_analyzed_at.tzinfo is None:
        last_analyzed_at = last_analyzed_at.replace(tzinfo=timezone.utc)
    days = (now - last_analyzed_at).total_seconds() / 86400
    if days >= 7:
        return 20.0   # stale ≥ 7 days: strong bonus
    if days >= 3:
        return 10.0   # 3-7 days: moderate bonus
    if days >= 1:
        return  3.0   # 1-3 days: small bonus
    return -30.0      # analyzed today: strong penalty → skip today


async def run_pre_screener(db: AsyncSession) -> dict:
    """
    Score all in-universe assets and activate top LONG/SHORT candidates.
    Pure DB operation — no external HTTP calls.
    """
    result = await db.execute(
        select(Asset.id, Asset.symbol, Asset.last_analyzed_at, Asset.long_score, Asset.short_score)
        .where(Asset.in_universe == True)
    )
    universe = result.fetchall()

    if not universe:
        logger.warning("Pre-screener: no universe stocks found — run universe loader first")
        return {"scored": 0, "long_activated": 0, "short_activated": 0}

    logger.info(f"Pre-screener: scoring {len(universe)} universe stocks (DB-only, no yfinance)")

    # Apply recency adjustment to stored scores
    scores: dict[str, tuple[float, float]] = {}
    for _id, sym, analyzed_at, long_s, short_s in universe:
        adj = _recency_adjustment(analyzed_at)
        scores[sym] = (max(0.0, long_s + adj), max(0.0, short_s + adj))

    # Rank by LONG score
    long_ranked = sorted(scores.items(), key=lambda x: x[1][0], reverse=True)
    long_top = {sym for sym, _ in long_ranked[:LONG_SLOTS]}

    # SHORT candidates: highest short_score EXCLUDING stocks already in LONG pool.
    # When all scores are tied (base=0, adj=30), long_ranked and short_ranked are
    # in the same order — so without this filter, short_top would be empty.
    short_ranked = sorted(scores.items(), key=lambda x: x[1][1], reverse=True)
    short_candidates = [sym for sym, _ in short_ranked if sym not in long_top]
    short_top = set(short_candidates[:SHORT_SLOTS])

    now = datetime.now(timezone.utc)

    # Deactivate ALL universe stocks in one query
    await db.execute(
        update(Asset)
        .where(Asset.in_universe == True)
        .values(is_active_in_pool=False, direction_bias="NEUTRAL")
    )

    # Bulk-activate LONG candidates (one UPDATE per symbol)
    for sym in long_top:
        long_s, short_s = scores[sym]
        await db.execute(
            update(Asset).where(Asset.symbol == sym).values(
                is_active_in_pool=True,
                direction_bias="LONG",
                long_score=long_s,
                short_score=short_s,
                screener_activated_at=now,
            )
        )

    # Bulk-activate SHORT candidates
    for sym in short_top:
        long_s, short_s = scores[sym]
        await db.execute(
            update(Asset).where(Asset.symbol == sym).values(
                is_active_in_pool=True,
                direction_bias="SHORT",
                long_score=long_s,
                short_score=short_s,
                screener_activated_at=now,
            )
        )

    await db.flush()

    long_activated = len(long_top)
    short_activated = len(short_top)
    logger.info(
        f"Pre-screener complete: scored={len(scores)}, "
        f"long={long_activated}, short={short_activated}"
    )
    return {
        "scored": len(scores),
        "long_activated": long_activated,
        "short_activated": short_activated,
        "top_long": [{"symbol": sym, "long_score": round(scores[sym][0], 1)} for sym, _ in long_ranked[:5]],
        "top_short": [{"symbol": sym, "short_score": round(scores[sym][1], 1)} for sym, _ in short_ranked if sym in short_top][:5],
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
