"""
Earnings Watcher — monitors universe stocks for fresh quarterly earnings.

Runs daily at 07:30 IL via APScheduler.

Two-stage logic:
  Stage 1 — Fetch Alpha Vantage upcoming calendar (0-14 days ahead).
             Add universe companies to a PENDING hash with their expected date.
  Stage 2 — Check PENDING hash: any company whose report_date <= today
             gets moved to CONFIRMED queue (they have actually reported by now).
  Trigger  — When CONFIRMED queue reaches MIN_EARNINGS_TRIGGER → quarterly scan.

This way we never show future dates as "already reported".

Redis keys:
  investment_ai:earnings_pending   HASH   — sym → {report_date, added_at}  (upcoming)
  investment_ai:earnings_queue     SET    — confirmed reporters (date passed)
  investment_ai:earnings_details   HASH   — sym → {earnings_date, added_at} (confirmed)
  investment_ai:earnings_last_check STRING — ISO timestamp of last run
  investment_ai:earnings_scan_triggered STRING — quarter when scan was triggered
"""
import csv
import io
import json
import logging
from datetime import datetime, timezone, timedelta

import httpx

logger = logging.getLogger(__name__)

REDIS_KEY_PENDING    = "investment_ai:earnings_pending"
REDIS_KEY_QUEUE      = "investment_ai:earnings_queue"
REDIS_KEY_DETAILS    = "investment_ai:earnings_details"
REDIS_KEY_LAST_CHECK = "investment_ai:earnings_last_check"
REDIS_KEY_TRIGGERED  = "investment_ai:earnings_scan_triggered"
REDIS_TTL = 90 * 24 * 3600


def _quarter_label(dt: datetime) -> str:
    return f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"


async def _fetch_alpha_vantage_earnings(api_key: str) -> list:
    """
    Fetch upcoming earnings calendar from Alpha Vantage (free tier).
    Returns list of dicts with at least: symbol, reportDate.
    """
    url = "https://www.alphavantage.co/query"
    params = {"function": "EARNINGS_CALENDAR", "horizon": "3month", "apikey": api_key}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
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
        logger.warning("[earnings_watcher] No API key configured — skipping")
        return {"skipped": True, "reason": "no_api_key"}

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    lookahead = today + timedelta(days=14)
    quarter = _quarter_label(today)

    logger.info(f"[earnings_watcher] running — today={today.date()}")

    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        # --- Load universe candidates (skip recently analyzed) ---
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
            return {"candidates": 0, "newly_pending": 0, "newly_confirmed": 0}

        # --- Stage 1: Fetch upcoming calendar → add to PENDING ---
        try:
            earnings_data = await _fetch_alpha_vantage_earnings(api_key)
        except Exception as e:
            logger.warning(f"[earnings_watcher] Alpha Vantage API failed: {e}")
            await redis_client.set(REDIS_KEY_LAST_CHECK, today.isoformat(), ex=REDIS_TTL)
            return {"error": str(e)}

        newly_pending = 0
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
            # Only add upcoming dates (today to 14 days ahead)
            if not (today <= report_date <= lookahead):
                continue
            # Add to pending if not already there
            existing = await redis_client.hget(REDIS_KEY_PENDING, sym)
            if not existing:
                await redis_client.hset(
                    REDIS_KEY_PENDING, sym,
                    json.dumps({"report_date": report_date_str, "added_at": today.isoformat()}),
                )
                await redis_client.expire(REDIS_KEY_PENDING, REDIS_TTL)
                newly_pending += 1

        # --- Stage 2: Check PENDING → move past-due companies to CONFIRMED ---
        all_pending = await redis_client.hgetall(REDIS_KEY_PENDING)
        newly_confirmed = 0
        for sym, val in all_pending.items():
            try:
                d = json.loads(val)
                report_date = datetime.strptime(d["report_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except Exception:
                continue
            # If report date has passed → company has reported → move to confirmed
            if report_date <= today:
                await redis_client.sadd(REDIS_KEY_QUEUE, sym)
                await redis_client.expire(REDIS_KEY_QUEUE, REDIS_TTL)
                await redis_client.hset(
                    REDIS_KEY_DETAILS, sym,
                    json.dumps({"earnings_date": d["report_date"], "added_at": today.isoformat()}),
                )
                await redis_client.expire(REDIS_KEY_DETAILS, REDIS_TTL)
                await redis_client.hdel(REDIS_KEY_PENDING, sym)
                newly_confirmed += 1

        queued_total = await redis_client.scard(REDIS_KEY_QUEUE)
        pending_total = await redis_client.hlen(REDIS_KEY_PENDING)
        await redis_client.set(REDIS_KEY_LAST_CHECK, today.isoformat(), ex=REDIS_TTL)

        logger.info(
            f"[earnings_watcher] pending={pending_total} | confirmed={queued_total} | "
            f"trigger_at={settings.MIN_EARNINGS_TRIGGER}"
        )

        result = {
            "candidates": len(candidates),
            "newly_pending": newly_pending,
            "newly_confirmed": newly_confirmed,
            "pending_total": int(pending_total),
            "queued_total": int(queued_total),
            "trigger_at": settings.MIN_EARNINGS_TRIGGER,
            "last_check": today.isoformat(),
        }

        if queued_total >= settings.MIN_EARNINGS_TRIGGER:
            logger.info(f"[earnings_watcher] threshold reached → triggering quarterly scan")
            try:
                scan_result = await trigger_quarterly_scan(quarter)
                result["scan_triggered"] = scan_result
                await redis_client.set(REDIS_KEY_TRIGGERED, quarter, ex=REDIS_TTL)
                await redis_client.delete(REDIS_KEY_QUEUE)
                await redis_client.delete(REDIS_KEY_DETAILS)
                await redis_client.delete(REDIS_KEY_PENDING)
                logger.info(f"[earnings_watcher] quarterly scan triggered for {quarter}")
            except Exception as e:
                logger.error(f"[earnings_watcher] trigger_quarterly_scan failed: {e}")
                result["trigger_error"] = str(e)

        return result

    finally:
        await redis_client.aclose()
