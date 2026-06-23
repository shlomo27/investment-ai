"""
Earnings Watcher — triggers quarterly AI scan based on earnings releases.

Logic:
  - Runs daily at 07:30 IL, but exits immediately outside earnings season.
  - Earnings seasons (when companies report quarterly results):
      Q4 prior year: Jan 15 – Mar 15   (fiscal end: Dec 31)
      Q1:            Apr 15 – Jun 15   (fiscal end: Mar 31)
      Q2:            Jul 15 – Sep 15   (fiscal end: Jun 30)
      Q3:            Oct 15 – Dec 15   (fiscal end: Sep 30)
  - During a season, for each eligible universe stock:
      1. Checks that the earnings REPORT DATE is within the last 10 days (fresh).
      2. Verifies that the most recent QUARTERLY FINANCIALS in yfinance match the
         expected fiscal quarter end (within 45-day tolerance). This prevents Claude
         from running analysis on stale/old financials even if the report date looked fresh.
  - Accumulates qualifying stocks in a Redis queue (set, no duplicates, 45-day TTL).
  - When queue >= MIN_EARNINGS_TRIGGER (default 20):
      → runs full Claude fundamental scan on those stocks only
      → clears queue
  - Deduplication: stocks with last_analyzed_at within 70 days are skipped entirely.

Admin reviews results and publishes master list when ready.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

EARNINGS_LOOKBACK_DAYS = 10       # days back to look for a fresh earnings report date
ALREADY_SCANNED_DAYS = 70         # skip stocks scanned within this many days (≈ 1 quarter)
FISCAL_QUARTER_TOLERANCE_DAYS = 45  # tolerance when matching fiscal quarter end date
REDIS_QUEUE_KEY = "investment_ai:earnings_scan_queue"
REDIS_QUEUE_TTL = 86400 * 45      # queue persists up to 45 days (one earnings season)


def _is_earnings_season() -> bool:
    """Returns True only during the 4 quarterly earnings reporting windows."""
    today = datetime.now(timezone.utc)
    m, d = today.month, today.day
    SEASONS: List[Tuple[int, int, int, int]] = [
        (1, 15, 3, 15),
        (4, 15, 6, 15),
        (7, 15, 9, 15),
        (10, 15, 12, 15),
    ]
    for sm, sd, em, ed in SEASONS:
        in_start = (m == sm and d >= sd) or (sm < m)
        in_end   = (m == em and d <= ed) or (m < em)
        if in_start and in_end and sm <= m <= em:
            return True
    return False


def _expected_fiscal_quarter_end() -> datetime:
    """
    Returns the expected fiscal quarter-end date for the earnings being published NOW.
    Companies report roughly 6 weeks after their quarter ends:
      Jan-Mar  → Q4 results → fiscal end Dec 31 (prior year)
      Apr-Jun  → Q1 results → fiscal end Mar 31
      Jul-Sep  → Q2 results → fiscal end Jun 30
      Oct-Dec  → Q3 results → fiscal end Sep 30
    """
    today = datetime.now(timezone.utc)
    year, month = today.year, today.month
    if month <= 3:
        return datetime(year - 1, 12, 31, tzinfo=timezone.utc)
    elif month <= 6:
        return datetime(year, 3, 31, tzinfo=timezone.utc)
    elif month <= 9:
        return datetime(year, 6, 30, tzinfo=timezone.utc)
    else:
        return datetime(year, 9, 30, tzinfo=timezone.utc)


async def _get_fresh_earnings_date(symbol: str) -> Optional[str]:
    """
    Returns the earnings release date (ISO string) only when BOTH conditions hold:
      1. The company's earnings REPORT DATE is within the last EARNINGS_LOOKBACK_DAYS.
      2. The most recent QUARTERLY FINANCIALS in yfinance match the expected fiscal
         quarter (within FISCAL_QUARTER_TOLERANCE_DAYS). This ensures Claude will
         analyze the NEW quarter's data, not a cached older quarter.

    Returns None if either condition fails.
    """
    expected_fiscal_end = _expected_fiscal_quarter_end()

    try:
        def _fetch() -> Optional[str]:
            import yfinance as yf
            ticker = yf.Ticker(symbol)

            # --- Condition 1: fresh earnings report date ---
            ed = ticker.earnings_dates
            if ed is None or ed.empty:
                return None
            reported = ed[ed["Reported EPS"].notna()]
            if reported.empty:
                return None
            most_recent_report = reported.index[0]
            report_cutoff = (
                datetime.now(timezone.utc).replace(tzinfo=None)
                - timedelta(days=EARNINGS_LOOKBACK_DAYS)
            )
            report_ts = (
                most_recent_report.tz_localize(None)
                if most_recent_report.tzinfo else most_recent_report
            )
            if report_ts < report_cutoff:
                return None  # report is not fresh

            # --- Condition 2: quarterly financials match expected fiscal quarter ---
            qfs = ticker.quarterly_income_stmt
            if qfs is None or qfs.empty:
                # Fallback: try balance sheet
                qfs = ticker.quarterly_balance_sheet
            if qfs is None or qfs.empty:
                logger.debug(f"[earnings_watcher] {symbol}: no quarterly financials available")
                return None  # can't verify — skip to be safe

            most_recent_fiscal = qfs.columns[0]
            fiscal_ts = (
                most_recent_fiscal.tz_localize(None)
                if most_recent_fiscal.tzinfo else most_recent_fiscal
            )
            expected_ts = expected_fiscal_end.replace(tzinfo=None)
            delta_days = abs((fiscal_ts - expected_ts).days)

            if delta_days > FISCAL_QUARTER_TOLERANCE_DAYS:
                logger.debug(
                    f"[earnings_watcher] {symbol}: fiscal quarter mismatch — "
                    f"yfinance has {fiscal_ts.date()}, expected ~{expected_ts.date()} "
                    f"(gap {delta_days}d > {FISCAL_QUARTER_TOLERANCE_DAYS}d tolerance) — skipping"
                )
                return None  # financials not yet updated for this quarter

            return report_ts.strftime("%Y-%m-%d")

        return await asyncio.get_event_loop().run_in_executor(None, _fetch)
    except Exception as e:
        logger.debug(f"[earnings_watcher] {symbol}: error: {e}")
        return None


async def job_earnings_queue_check():
    """
    Daily APScheduler entry point (07:30 IL).

    Steps:
      1. Exit immediately if not in an earnings season.
      2. Load universe stocks; filter out those already scanned this quarter
         (last_analyzed_at within ALREADY_SCANNED_DAYS).
      3. Check remaining stocks via yfinance — fresh report date AND matching
         fiscal quarter financials must both be confirmed.
      4. Add qualifying stocks to Redis queue.
      5. When queue >= MIN_EARNINGS_TRIGGER → run Claude scan, clear queue.
    """
    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.db.models.asset import Asset
    from sqlalchemy import select
    import redis.asyncio as aioredis

    if not _is_earnings_season():
        logger.info("[earnings_watcher] Not in earnings season — skipping")
        return

    min_trigger = getattr(settings, "MIN_EARNINGS_TRIGGER", 20)
    expected_qtr = _expected_fiscal_quarter_end().strftime("%Y-Q%m")  # approx label for logs
    logger.info(
        f"[earnings_watcher] Earnings season — daily check "
        f"(expected quarter end: {_expected_fiscal_quarter_end().date()}, trigger={min_trigger})"
    )

    redis_client = aioredis.from_url(settings.REDIS_URL)

    try:
        # 1. Load universe, skip recently scanned stocks
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
            f"[earnings_watcher] Universe: {len(all_assets)} — "
            f"{skipped} already scanned this quarter, {len(fresh_pool)} eligible to check"
        )

        if not fresh_pool:
            logger.info("[earnings_watcher] All universe stocks already scanned this quarter")
            return

        # 2. Check earnings (batched to respect yfinance rate limits)
        BATCH = 15
        newly_queued: List[str] = []

        for i in range(0, len(fresh_pool), BATCH):
            batch = fresh_pool[i: i + BATCH]
            results = await asyncio.gather(
                *[_get_fresh_earnings_date(sym) for sym in batch],
                return_exceptions=True,
            )
            for sym, result in zip(batch, results):
                if isinstance(result, str):
                    already_in_queue = await redis_client.sismember(REDIS_QUEUE_KEY, sym)
                    if not already_in_queue:
                        await redis_client.sadd(REDIS_QUEUE_KEY, sym)
                        await redis_client.expire(REDIS_QUEUE_KEY, REDIS_QUEUE_TTL)
                        newly_queued.append(sym)
                        logger.info(
                            f"[earnings_watcher] Queued {sym} "
                            f"(report date: {result}, fiscal data verified)"
                        )

            await asyncio.sleep(3)

        # 3. Check trigger threshold
        queue_size = await redis_client.scard(REDIS_QUEUE_KEY)
        logger.info(
            f"[earnings_watcher] Queue: {queue_size} stocks "
            f"({len(newly_queued)} added today, trigger={min_trigger})"
        )

        if queue_size >= min_trigger:
            # The fresh-earnings stocks are the TRIGGER only.
            # The actual scan covers the FULL universe (~900 stocks), not just these.
            trigger_symbols = [
                s.decode() if isinstance(s, bytes) else s
                for s in await redis_client.smembers(REDIS_QUEUE_KEY)
            ]
            await redis_client.delete(REDIS_QUEUE_KEY)  # clear trigger queue

            fe = _expected_fiscal_quarter_end()
            q_num = (fe.month - 1) // 3 + 1
            quarter = f"Q{q_num}-{fe.year}"

            logger.info(
                f"[earnings_watcher] {len(trigger_symbols)} fresh-earnings stocks "
                f"triggered full universe scan — {quarter}"
            )

            from app.workers.quarterly_scanner import trigger_quarterly_scan
            started = await trigger_quarterly_scan(quarter=quarter)
            if not started:
                logger.info("[earnings_watcher] Quarterly scan already running — trigger ignored")
        else:
            logger.info(
                f"[earnings_watcher] Accumulating — "
                f"{queue_size}/{min_trigger}, waiting for more earnings releases"
            )

    finally:
        await redis_client.aclose()


# Note: _run_earnings_scan removed — earnings_watcher now only accumulates the trigger.
# The actual full-universe scan is handled by quarterly_scanner.trigger_quarterly_scan().
