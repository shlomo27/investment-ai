"""
Earnings Watcher — monitors universe stocks for fresh quarterly earnings.

Runs daily at 07:30 IL via APScheduler.

Uses Alpha Vantage EARNINGS_CALENDAR endpoint (free, no per-symbol calls)
to detect companies that are reporting earnings within a 3-month window,
then cross-references with universe symbols to find those that just reported
in the last 10 days.

When ≥ MIN_EARNINGS_TRIGGER unique symbols are queued → triggers the
full-universe quarterly scan.

No hardcoded calendar windows — works year-round because many companies
(e.g. Micron, Oracle) have non-standard fiscal years.

Redis keys:
  investment_ai:earnings_queue      SET    — symbols pending scan trigger
  investment_ai:earnings_details    HASH   — symbol → {earnings_date, added_at}
  investment_ai:earnings_last_check STRING — ISO timestamp of last run
  investment_ai:earnings_scan_triggered STRING — quarter label when triggered
"""
import csv
import io
import json
import logging
from datetime import datetime, timezone, timedelta

import httpx

logger = logging.getLogger(__name__)

REDIS_KEY_QUEUE      = "investment_ai:earnings_queue"
REDIS_KEY_DETAILS    = "investment_ai:earnings_details"
REDIS_KEY_LAST_CHECK = "investment_ai:earnings_last_check"
REDIS_KEY_TRIGGERED  = "investment_ai:earnings_scan_triggered"
REDIS_TTL = 90 * 24 * 3600   # 90 days


def _quarter_label(dt: datetime) -> str:
    return f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"


async def _fetch_alpha_vantage_earnings(api_key: str) -> list:
    """
    Alpha Vantage EARNINGS_CALENDAR — single call, returns CSV of all
    companies reporting earnings in the next 3 months.
    Free tier: unlimited calls for this endpoint.
    Returns list of dicts: {symbol, reportDate, ...}
    """
    url = "https://www.alphavantage.co/query"
    params = {"function": "EARNINGS_CALENDAR", "horizon": "3month", "apikey": api_key}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        # Response is CSV
        reader = csv.DictReader(io.StringIO(resp.text))
        return list(reader)


async def job_earnings_queue_check() -> dict:
    """APScheduler entry point — daily 07:30 IL."""
    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.db.models.asset import Asset
    from app.workers.quarterly_scanner import trigger_quarterly_scan
    from sqlalchemy import select
    import redis.asyncio as aioredis

    api_key = settings.ALPHA_VANTAGE_KEY or settings.FMP_API_KEY
    if not api_key:
        logger.warning("[earnings_watcher] No API key configured (ALPHA_VANTAGE_KEY or FMP_API_KEY) — skipping")
        return {"skipped": True, "reason": "no_api_key"}

    today = datetime.now(timezone.utc)
    cutoff_past = today - timedelta(days=10)   # reported in last 10 days
    quarter = _quarter_label(today)

    logger.info(f"[earnings_watcher] checking for fresh earnings (last 10 days)")

    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        # Load universe — skip symbols analyzed within the last 70 days
        cutoff_analyzed = today - timedelta(days=70)
        async with AsyncSessionLocal() as db:
            rows = await db.execute(select(Asset.symbol, Asset.last_analyzed_at))
            universe_map = {r[0]: r[1] for r in rows.all()}

        candidates: set = set()
        for sym, last in universe_map.items():
            if last is None:
                candidates.add(sym)
            else:
                last_utc = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
                if last_utc < cutoff_analyzed:
                    candidates.add(sym)

        if not candidates:
            logger.info("[earnings_watcher] all universe stocks recently analyzed — skipping")
            return {"candidates": 0, "fresh": 0}

        logger.info(f"[earnings_watcher] {len(candidates)} candidates | fetching Alpha Vantage calendar")

        # Fetch earnings calendar
        try:
            earnings_data = await _fetch_alpha_vantage_earnings(api_key)
        except Exception as e:
            logger.warning(f"[earnings_watcher] Alpha Vantage API failed: {e}")
            await redis_client.set(REDIS_KEY_LAST_CHECK, today.isoformat(), ex=REDIS_TTL)
            return {"error": str(e), "last_check": today.isoformat()}

        # Cross-reference: company in universe AND report date within [-10 days, +3 days]
        # Alpha Vantage returns upcoming earnings — include dates slightly in the future
        # so we catch companies that reported just before this run, and ones about to report.
        lookahead = today + timedelta(days=3)
        fresh_count = 0
        for item in earnings_data:
            sym = item.get("symbol", "").upper()
            if sym not in candidates:
                continue
            report_date_str = item.get("reportDate", "")
            if not report_date_str:
                continue
            try:
                report_date = datetime.strptime(report_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            # Include report dates in last 10 days OR next 3 days
            if not (cutoff_past <= report_date <= lookahead):
                continue

            await redis_client.sadd(REDIS_KEY_QUEUE, sym)
            await redis_client.expire(REDIS_KEY_QUEUE, REDIS_TTL)
            await redis_client.hset(
                REDIS_KEY_DETAILS, sym,
                json.dumps({"earnings_date": report_date_str, "added_at": today.isoformat()}),
            )
            await redis_client.expire(REDIS_KEY_DETAILS, REDIS_TTL)
            fresh_count += 1

        queued_total = await redis_client.scard(REDIS_KEY_QUEUE)
        await redis_client.set(REDIS_KEY_LAST_CHECK, today.isoformat(), ex=REDIS_TTL)

        logger.info(
            f"[earnings_watcher] {fresh_count} fresh this run | "
            f"queue: {queued_total}/{settings.MIN_EARNINGS_TRIGGER}"
        )

        result = {
            "candidates": len(candidates),
            "fresh_this_run": fresh_count,
            "queued_total": int(queued_total),
            "trigger_at": settings.MIN_EARNINGS_TRIGGER,
            "last_check": today.isoformat(),
        }

        if queued_total >= settings.MIN_EARNINGS_TRIGGER:
            logger.info(f"[earnings_watcher] threshold reached ({queued_total}) → triggering quarterly scan")
            try:
                scan_result = await trigger_quarterly_scan(quarter)
                result["scan_triggered"] = scan_result
                await redis_client.set(REDIS_KEY_TRIGGERED, quarter, ex=REDIS_TTL)
                await redis_client.delete(REDIS_KEY_QUEUE)
                await redis_client.delete(REDIS_KEY_DETAILS)
                logger.info(f"[earnings_watcher] quarterly scan triggered for {quarter}")
            except Exception as e:
                logger.error(f"[earnings_watcher] trigger_quarterly_scan failed: {e}")
                result["trigger_error"] = str(e)

        return result

    finally:
        await redis_client.aclose()
