"""
Pre-Screener
Selects 100 stocks per day from the ~900-stock universe for full AI analysis.

Selection logic: pure recency rotation — stocks not analyzed recently get
priority. The AI in the full scan decides BUY/SELL/HOLD freely, with no
pre-assigned direction bias.

Rotation cycle: 100 stocks/day × 9 days ≈ full S&P500+S&P400 coverage.
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

POOL_SIZE = 100  # stocks selected per day for AI analysis


def _recency_score(last_analyzed_at: Optional[datetime]) -> float:
    """
    Priority score based on how long since last AI analysis.
    Never analyzed = highest priority; analyzed today = lowest.
    """
    if last_analyzed_at is None:
        return 30.0
    now = datetime.now(timezone.utc)
    if last_analyzed_at.tzinfo is None:
        last_analyzed_at = last_analyzed_at.replace(tzinfo=timezone.utc)
    days = (now - last_analyzed_at).total_seconds() / 86400
    if days >= 7:
        return 20.0
    if days >= 3:
        return 10.0
    if days >= 1:
        return  3.0
    return -30.0  # analyzed today → skip


async def run_pre_screener(db: AsyncSession) -> dict:
    """
    Select the top POOL_SIZE universe stocks by recency and mark them active.
    No direction bias assigned — the AI decides BUY/SELL/HOLD freely.
    """
    result = await db.execute(
        select(Asset.id, Asset.symbol, Asset.last_analyzed_at)
        .where(Asset.in_universe == True)
    )
    universe = result.fetchall()

    if not universe:
        logger.warning("Pre-screener: no universe stocks — run universe loader first")
        return {"scored": 0, "activated": 0}

    logger.info(f"Pre-screener: ranking {len(universe)} universe stocks by recency")

    # Score and rank — pure recency, no yfinance.
    # Tiebreaker: symbol alphabetically so equal-scored stocks always rank
    # in the same order → same 100 selected every run until scans update last_analyzed_at.
    scored = [
        (sym, _recency_score(analyzed_at))
        for _id, sym, analyzed_at in universe
    ]
    ranked = sorted(scored, key=lambda x: (-x[1], x[0]))
    top_100 = [sym for sym, _ in ranked[:POOL_SIZE]]
    top_set = set(top_100)

    now = datetime.now(timezone.utc)

    # Deactivate all universe stocks
    await db.execute(
        update(Asset)
        .where(Asset.in_universe == True)
        .values(is_active_in_pool=False, direction_bias="NEUTRAL")
    )

    # Activate top 100 with no direction bias
    for sym, score in ranked[:POOL_SIZE]:
        await db.execute(
            update(Asset).where(Asset.symbol == sym).values(
                is_active_in_pool=True,
                direction_bias="NEUTRAL",
                long_score=max(0.0, score),
                screener_activated_at=now,
            )
        )

    await db.flush()

    activated = len(top_100)
    logger.info(f"Pre-screener complete: scored={len(universe)}, activated={activated}")
    return {
        "scored": len(universe),
        "activated": activated,
        "top_candidates": [
            {"symbol": sym, "score": round(score, 1)}
            for sym, score in ranked[:10]
        ],
    }


@celery_app.task(name="run_pre_screener", bind=True, max_retries=1)
def run_pre_screener_task(self):
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
