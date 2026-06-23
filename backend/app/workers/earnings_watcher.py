"""
Earnings Watcher — triggers quarterly AI scan based on earnings releases.

Logic:
  - Runs daily at 07:00 IL
  - Checks which universe stocks published earnings in the last 10 days (yfinance)
  - Accumulates them in a Redis queue (set — no duplicates)
  - When queue reaches MIN_EARNINGS_TRIGGER (default 20):
      → runs full Claude fundamental scan on all queued stocks
      → clears queue
  - Admin then reviews results and publishes master list

This replaces the fixed-date quarterly trigger: the scan fires naturally
as earnings season unfolds, using only stocks with fresh, current data.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)

EARNINGS_LOOKBACK_DAYS = 10     # days back to look for "fresh" earnings
REDIS_QUEUE_KEY = "investment_ai:earnings_scan_queue"
REDIS_QUEUE_TTL = 86400 * 45   # queue persists up to 45 days (covers one earnings season)


async def _get_fresh_earnings_date(symbol: str) -> Optional[str]:
    """
    Return the earnings release date (ISO string) if the stock published earnings
    within the last EARNINGS_LOOKBACK_DAYS days, otherwise None.
    Uses yfinance earnings_dates — one API call per symbol.
    """
    try:
        def _fetch():
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            ed = ticker.earnings_dates
            if ed is None or ed.empty:
                return None
            # earnings_dates: index=DatetimeIndex (newest first), col="Reported EPS"
            reported = ed[ed["Reported EPS"].notna()]
            if reported.empty:
                return None
            most_recent = reported.index[0]
            # Normalize to UTC-naive for comparison
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=EARNINGS_LOOKBACK_DAYS)
            ts = most_recent.tz_localize(None) if most_recent.tzinfo else most_recent
            if ts >= cutoff:
                return ts.strftime("%Y-%m-%d")
            return None

        return await asyncio.get_event_loop().run_in_executor(None, _fetch)
    except Exception as e:
        logger.debug(f"[earnings_watcher] {symbol}: earnings fetch error: {e}")
        return None


async def job_earnings_queue_check():
    """
    Daily APScheduler entry point.
    Checks the universe for fresh earnings and fires a scan when queue >= MIN_EARNINGS_TRIGGER.
    """
    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.db.models.asset import Asset
    from sqlalchemy import select
    import redis.asyncio as aioredis

    min_trigger = getattr(settings, "MIN_EARNINGS_TRIGGER", 20)
    logger.info(f"[earnings_watcher] Daily earnings check starting (trigger={min_trigger})")

    redis_client = aioredis.from_url(settings.REDIS_URL)

    try:
        # 1. Load all universe stocks
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(Asset.symbol).where(Asset.in_universe == True)
            )
            symbols = [r[0] for r in rows.all()]

        logger.info(f"[earnings_watcher] Scanning {len(symbols)} universe stocks for fresh earnings")

        # 2. Check earnings in batches (gentle on yfinance rate limits)
        BATCH = 15
        newly_queued: List[str] = []

        for i in range(0, len(symbols), BATCH):
            batch = symbols[i: i + BATCH]
            results = await asyncio.gather(
                *[_get_fresh_earnings_date(sym) for sym in batch],
                return_exceptions=True,
            )
            for sym, result in zip(batch, results):
                if isinstance(result, str):
                    already = await redis_client.sismember(REDIS_QUEUE_KEY, sym)
                    if not already:
                        await redis_client.sadd(REDIS_QUEUE_KEY, sym)
                        await redis_client.expire(REDIS_QUEUE_KEY, REDIS_QUEUE_TTL)
                        newly_queued.append(sym)
                        logger.info(f"[earnings_watcher] Queued {sym} (earnings: {result})")

            await asyncio.sleep(3)  # 3s between batches to avoid yfinance rate limit

        # 3. Check if we've reached the trigger threshold
        queue_size = await redis_client.scard(REDIS_QUEUE_KEY)
        logger.info(
            f"[earnings_watcher] Queue: {queue_size} stocks "
            f"({len(newly_queued)} new today, trigger={min_trigger})"
        )

        if queue_size >= min_trigger:
            queued = [s.decode() if isinstance(s, bytes) else s
                      for s in await redis_client.smembers(REDIS_QUEUE_KEY)]
            logger.info(f"[earnings_watcher] Threshold reached — triggering scan for {len(queued)} stocks")
            # Clear queue BEFORE scan so a crash doesn't cause duplicate scans
            await redis_client.delete(REDIS_QUEUE_KEY)
            await _run_earnings_scan(queued)
        else:
            logger.info(
                f"[earnings_watcher] Waiting for more earnings "
                f"({queue_size}/{min_trigger} so far)"
            )

    finally:
        await redis_client.aclose()


async def _run_earnings_scan(symbols: List[str]):
    """Run full Claude fundamental scan for a list of symbols with fresh earnings."""
    from app.core.database import AsyncSessionLocal
    from app.db.models.asset import Asset
    from app.agents.workflow import run_investment_workflow
    from sqlalchemy import select

    logger.info(f"[earnings_watcher] Earnings-triggered scan: {len(symbols)} stocks")

    # Fetch exchange + direction_bias for each symbol
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(Asset.symbol, Asset.exchange, Asset.direction_bias)
            .where(Asset.symbol.in_(symbols))
        )
        asset_map = {r[0]: (r[1], r[2]) for r in rows.all()}

    BATCH = 3
    approved = rejected = errors = 0

    for i in range(0, len(symbols), BATCH):
        batch = symbols[i: i + BATCH]
        results = await asyncio.gather(
            *[
                run_investment_workflow(
                    symbol=sym,
                    exchange=asset_map[sym][0].value if sym in asset_map else "NASDAQ",
                    direction_bias=asset_map[sym][1] if sym in asset_map else "NEUTRAL",
                    trigger_type="EARNINGS",
                    trigger_details="Earnings-triggered quarterly scan",
                    language="he",
                )
                for sym in batch
            ],
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, Exception):
                errors += 1
                logger.warning(f"[earnings_watcher] Scan error: {r}")
            elif isinstance(r, dict):
                if r.get("workflow_status") in ("completed", "saved"):
                    approved += 1
                else:
                    rejected += 1
        await asyncio.sleep(2)

    logger.info(
        f"[earnings_watcher] Earnings scan done: "
        f"total={len(symbols)}, approved={approved}, rejected={rejected}, errors={errors}"
    )
