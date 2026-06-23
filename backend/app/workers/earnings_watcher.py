"""
Earnings Watcher — triggers quarterly AI scan based on earnings releases.

Logic:
  - Runs daily at 07:30 IL, but exits immediately outside earnings season
  - Earnings seasons (when companies report quarterly results):
      Q4 prior year: Jan 15 – Mar 15
      Q1:            Apr 15 – Jun 15
      Q2:            Jul 15 – Sep 15
      Q3:            Oct 15 – Dec 15
  - During a season: checks which universe stocks published earnings in the
    last EARNINGS_LOOKBACK_DAYS (10) days AND have not been scanned this quarter
  - Accumulates qualifying stocks in a Redis queue (set — no duplicates, 45-day TTL)
  - When queue reaches MIN_EARNINGS_TRIGGER (default 20):
      → runs full Claude fundamental scan on all queued stocks
      → clears queue (scan can fire multiple times per season if more stocks come in)
  - Deduplication: stocks whose last_analyzed_at is within the last 70 days
    are skipped — they were already covered in this earnings cycle

Admin reviews results and publishes master list when ready.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

EARNINGS_LOOKBACK_DAYS = 10       # days back to look for "fresh" earnings
ALREADY_SCANNED_DAYS = 70         # skip stocks scanned within this many days (≈1 quarter)
REDIS_QUEUE_KEY = "investment_ai:earnings_scan_queue"
REDIS_QUEUE_TTL = 86400 * 45      # queue persists up to 45 days (one earnings season)


def _is_earnings_season() -> bool:
    """
    Returns True only during the 4 quarterly earnings reporting windows.
    Outside these windows the watcher exits immediately without yfinance calls.
    """
    today = datetime.now(timezone.utc)
    m, d = today.month, today.day
    # (start_month, start_day, end_month, end_day)
    SEASONS: List[Tuple[int, int, int, int]] = [
        (1, 15, 3, 15),   # Q4 prior-year results: Jan 15 – Mar 15
        (4, 15, 6, 15),   # Q1 results:            Apr 15 – Jun 15
        (7, 15, 9, 15),   # Q2 results:            Jul 15 – Sep 15
        (10, 15, 12, 15), # Q3 results:            Oct 15 – Dec 15
    ]
    for sm, sd, em, ed in SEASONS:
        in_start = (m == sm and d >= sd) or (m > sm)
        in_end   = (m == em and d <= ed) or (m < em)
        if in_start and in_end and sm <= m <= em:
            return True
    return False


async def _get_fresh_earnings_date(symbol: str) -> Optional[str]:
    """
    Return the earnings release date (ISO string) if the stock published earnings
    within the last EARNINGS_LOOKBACK_DAYS days, otherwise None.
    One yfinance API call per symbol, run in a thread executor.
    """
    try:
        def _fetch():
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            ed = ticker.earnings_dates
            if ed is None or ed.empty:
                return None
            # earnings_dates: index=DatetimeIndex (newest first), col "Reported EPS"
            reported = ed[ed["Reported EPS"].notna()]
            if reported.empty:
                return None
            most_recent = reported.index[0]
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
    Daily APScheduler entry point (07:30 IL).

    Steps:
      1. Exit immediately if not in an earnings season.
      2. Load universe stocks, filter out those already scanned this quarter
         (last_analyzed_at within ALREADY_SCANNED_DAYS).
      3. Check remaining stocks for fresh earnings via yfinance (batched).
      4. Add qualifying stocks to Redis queue.
      5. When queue >= MIN_EARNINGS_TRIGGER → trigger Claude scan, clear queue.
    """
    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.db.models.asset import Asset
    from sqlalchemy import select
    import redis.asyncio as aioredis

    # Guard: only run during earnings reporting windows
    if not _is_earnings_season():
        logger.info("[earnings_watcher] Not in earnings season — skipping today")
        return

    min_trigger = getattr(settings, "MIN_EARNINGS_TRIGGER", 20)
    logger.info(f"[earnings_watcher] Earnings season — daily check starting (trigger={min_trigger})")

    redis_client = aioredis.from_url(settings.REDIS_URL)

    try:
        # 1. Load universe stocks, skip those recently scanned (already covered this quarter)
        already_scanned_cutoff = datetime.now(timezone.utc) - timedelta(days=ALREADY_SCANNED_DAYS)

        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(Asset.symbol, Asset.last_analyzed_at)
                .where(Asset.in_universe == True)
            )
            all_assets = rows.all()

        fresh_pool = [
            sym for sym, analyzed_at in all_assets
            if analyzed_at is None or analyzed_at < already_scanned_cutoff
        ]
        skipped = len(all_assets) - len(fresh_pool)
        logger.info(
            f"[earnings_watcher] Universe: {len(all_assets)} stocks — "
            f"{skipped} already scanned this quarter, {len(fresh_pool)} to check"
        )

        if not fresh_pool:
            logger.info("[earnings_watcher] All universe stocks already scanned this quarter")
            return

        # 2. Check earnings in batches (gentle on yfinance rate limits)
        BATCH = 15
        newly_queued: List[str] = []

        for i in range(0, len(fresh_pool), BATCH):
            batch = fresh_pool[i: i + BATCH]
            results = await asyncio.gather(
                *[_get_fresh_earnings_date(sym) for sym in batch],
                return_exceptions=True,
            )
            for sym, result in zip(batch, results):
                if isinstance(result, str):  # has fresh earnings date
                    already_in_queue = await redis_client.sismember(REDIS_QUEUE_KEY, sym)
                    if not already_in_queue:
                        await redis_client.sadd(REDIS_QUEUE_KEY, sym)
                        await redis_client.expire(REDIS_QUEUE_KEY, REDIS_QUEUE_TTL)
                        newly_queued.append(sym)
                        logger.info(f"[earnings_watcher] Queued {sym} (earnings released: {result})")

            await asyncio.sleep(3)  # rate-limit between batches

        # 3. Check trigger threshold
        queue_size = await redis_client.scard(REDIS_QUEUE_KEY)
        logger.info(
            f"[earnings_watcher] Queue: {queue_size} stocks "
            f"({len(newly_queued)} added today, trigger={min_trigger})"
        )

        if queue_size >= min_trigger:
            queued = [
                s.decode() if isinstance(s, bytes) else s
                for s in await redis_client.smembers(REDIS_QUEUE_KEY)
            ]
            logger.info(
                f"[earnings_watcher] Threshold reached — "
                f"triggering Claude scan for {len(queued)} stocks"
            )
            # Clear queue BEFORE scan to prevent duplicate runs on crash/retry
            await redis_client.delete(REDIS_QUEUE_KEY)
            await _run_earnings_scan(queued)
        else:
            logger.info(
                f"[earnings_watcher] Accumulating — {queue_size}/{min_trigger} so far, "
                f"waiting for more earnings releases"
            )

    finally:
        await redis_client.aclose()


async def _run_earnings_scan(symbols: List[str]):
    """Run full Claude fundamental scan for symbols that have fresh earnings."""
    from app.core.database import AsyncSessionLocal
    from app.db.models.asset import Asset
    from app.agents.workflow import run_investment_workflow
    from sqlalchemy import select

    logger.info(f"[earnings_watcher] Starting earnings scan: {len(symbols)} stocks")

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
        f"[earnings_watcher] Scan complete: "
        f"total={len(symbols)}, approved={approved}, rejected={rejected}, errors={errors}"
    )
