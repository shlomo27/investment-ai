"""
Earnings Watcher — monitors universe stocks for fresh quarterly earnings.

Runs daily at 07:30 IL, ONLY during 4 earnings seasons:
  Jan 15 – Feb 28, Apr 15 – May 31, Jul 15 – Aug 31, Oct 15 – Nov 30

Two-step verification:
  1. yfinance earnings_dates: report date within last 10 days
  2. quarterly_income_stmt: most recent quarter matches expected fiscal quarter (±45 days)

Accumulates in Redis set. When ≥ MIN_EARNINGS_TRIGGER unique symbols queued →
triggers full-universe quarterly scan.

Skips stocks with last_analyzed_at within 70 days.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

import yfinance as yf

logger = logging.getLogger(__name__)

REDIS_KEY_EARNINGS = "investment_ai:earnings_queue"
REDIS_TTL_EARNINGS = 90 * 24 * 3600


def _is_earnings_season() -> bool:
    today = datetime.now(timezone.utc)
    month, day = today.month, today.day
    for sm, sd, em, ed in [(1,15,2,28),(4,15,5,31),(7,15,8,31),(10,15,11,30)]:
        start = today.replace(month=sm, day=sd)
        end   = today.replace(month=em, day=ed)
        if start <= today <= end:
            return True
    return False


def _current_quarter_label() -> str:
    today = datetime.now(timezone.utc)
    q = (today.month - 1) // 3 + 1
    return f"{today.year}-Q{q}"


def _expected_fiscal_quarter_end() -> datetime:
    today = datetime.now(timezone.utc)
    year, month = today.year, today.month
    if month <= 3:   return datetime(year-1, 12, 31, tzinfo=timezone.utc)
    elif month <= 6: return datetime(year,   3,  31, tzinfo=timezone.utc)
    elif month <= 9: return datetime(year,   6,  30, tzinfo=timezone.utc)
    else:            return datetime(year,   9,  30, tzinfo=timezone.utc)


def _has_fresh_earnings(symbol: str) -> bool:
    try:
        tk = yf.Ticker(symbol)
        today = datetime.now(timezone.utc)

        dates = tk.earnings_dates
        if dates is None or dates.empty:
            return False
        most_recent = dates.index[0]
        if hasattr(most_recent, 'tzinfo') and most_recent.tzinfo:
            most_recent = most_recent.astimezone(timezone.utc)
        else:
            most_recent = most_recent.replace(tzinfo=timezone.utc)
        if (today - most_recent).days > 10:
            return False

        income = tk.quarterly_income_stmt
        if income is None or income.empty:
            return False
        lqd = income.columns[0]
        if hasattr(lqd, 'tzinfo') and lqd.tzinfo:
            lqd = lqd.astimezone(timezone.utc)
        else:
            lqd = datetime(lqd.year, lqd.month, lqd.day, tzinfo=timezone.utc)
        expected = _expected_fiscal_quarter_end()
        if abs((lqd - expected).days) > 45:
            return False

        return True
    except Exception as e:
        logger.debug(f"[earnings_watcher] {symbol}: {e}")
        return False


async def job_earnings_queue_check() -> dict:
    """APScheduler entry point — daily 07:30 IL."""
    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.db.models.asset import Asset
    from app.workers.quarterly_scanner import trigger_quarterly_scan
    from sqlalchemy import select
    import redis.asyncio as aioredis

    if not _is_earnings_season():
        logger.debug("[earnings_watcher] not earnings season — skipping")
        return {"skipped": True, "reason": "not_earnings_season"}

    quarter = _current_quarter_label()
    logger.info(f"[earnings_watcher] checking {quarter}")

    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=70)
        async with AsyncSessionLocal() as db:
            rows = await db.execute(select(Asset.symbol, Asset.last_analyzed_at))
            candidates = [r[0] for r in rows.all() if r[1] is None or r[1] < cutoff]

        if not candidates:
            return {"candidates": 0, "fresh": 0}

        logger.info(f"[earnings_watcher] {len(candidates)} candidates")
        loop = asyncio.get_event_loop()
        fresh_count = 0

        for i in range(0, len(candidates), 10):
            batch = candidates[i:i+10]
            results = await asyncio.gather(
                *[loop.run_in_executor(None, _has_fresh_earnings, sym) for sym in batch],
                return_exceptions=True,
            )
            for sym, res in zip(batch, results):
                if res is True:
                    await redis_client.sadd(REDIS_KEY_EARNINGS, sym)
                    await redis_client.expire(REDIS_KEY_EARNINGS, REDIS_TTL_EARNINGS)
                    fresh_count += 1
            await asyncio.sleep(1)

        queued_total = await redis_client.scard(REDIS_KEY_EARNINGS)
        logger.info(f"[earnings_watcher] {fresh_count} fresh | queue: {queued_total}/{settings.MIN_EARNINGS_TRIGGER}")

        result = {"candidates": len(candidates), "fresh": fresh_count,
                  "queued_total": queued_total, "trigger_at": settings.MIN_EARNINGS_TRIGGER}

        if queued_total >= settings.MIN_EARNINGS_TRIGGER:
            logger.info(f"[earnings_watcher] threshold reached → triggering scan")
            scan_result = await trigger_quarterly_scan(quarter)
            result["scan_triggered"] = scan_result
            await redis_client.delete(REDIS_KEY_EARNINGS)

        return result
    finally:
        await redis_client.aclose()
