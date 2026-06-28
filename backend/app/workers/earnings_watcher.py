"""
Earnings Watcher — monitors universe stocks for fresh quarterly earnings.

Runs daily at 07:30 IL via APScheduler.

Three-stage logic:
  Stage 0 — SEC EDGAR lookback (free, no key needed).
             Searches for 8-K Item 2.02 filings in the last 14 days.
             Directly confirms any universe company that already filed earnings.
  Stage 1 — Alpha Vantage upcoming calendar (0-14 days ahead).
             Adds universe companies to PENDING with their expected report date.
  Stage 2 — Check PENDING: companies whose date has passed → move to CONFIRMED.
  Trigger  — When CONFIRMED queue ≥ MIN_EARNINGS_TRIGGER → quarterly scan.

Redis keys:
  investment_ai:earnings_pending      HASH   — sym → {report_date, added_at}
  investment_ai:earnings_queue        SET    — confirmed reporters
  investment_ai:earnings_details      HASH   — sym → {earnings_date, added_at}
  investment_ai:earnings_last_check   STRING — ISO timestamp of last run
  investment_ai:earnings_scan_triggered STRING — quarter when triggered
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

EDGAR_HEADERS = {"User-Agent": "InvestmentAI/1.0 admin@investment-ai.com"}


def _quarter_label(dt: datetime) -> str:
    return f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"


async def _edgar_recent_reporters(from_date: str, to_date: str, universe: set) -> list:
    """
    SEC EDGAR Stage 0 — find universe companies that filed 8-K Item 2.02
    (Results of Operations = earnings release) in the given date range.
    Free, no API key required. Companies must file within 4 business days.
    Returns list of (symbol, file_date) tuples.
    """
    try:
        async with httpx.AsyncClient(timeout=30, headers=EDGAR_HEADERS) as client:
            # Build CIK → ticker map from SEC's company tickers file
            tickers_resp = await client.get("https://www.sec.gov/files/company_tickers.json")
            tickers_data = tickers_resp.json()

        ticker_to_cik: dict = {}
        for entry in tickers_data.values():
            ticker = entry.get("ticker", "").upper()
            if ticker in universe:
                cik_str = str(entry["cik_str"]).zfill(10)
                ticker_to_cik[ticker] = cik_str
        cik_to_ticker = {v: k for k, v in ticker_to_cik.items()}

        # Search EDGAR EFTS for recent 8-K filings mentioning "Item 2.02"
        found: dict = {}   # cik → file_date
        async with httpx.AsyncClient(timeout=30, headers=EDGAR_HEADERS) as client:
            params = {
                "q": '"Item 2.02"',
                "forms": "8-K",
                "dateRange": "custom",
                "startdt": from_date,
                "enddt": to_date,
            }
            for from_idx in range(0, 500, 100):
                params["from"] = str(from_idx)
                resp = await client.get(
                    "https://efts.sec.gov/LATEST/search-index",
                    params=params,
                )
                data = resp.json()
                hits = data.get("hits", {}).get("hits", [])
                if not hits:
                    break
                for hit in hits:
                    src = hit.get("_source", {})
                    file_date = src.get("file_date", to_date)
                    for cik in src.get("ciks", []):
                        padded = cik.zfill(10)
                        if padded not in found:
                            found[padded] = file_date
                if len(hits) < 100:
                    break

        # Cross-reference with universe
        reporters = []
        for cik, file_date in found.items():
            ticker = cik_to_ticker.get(cik)
            if ticker:
                reporters.append((ticker, file_date))

        logger.info(f"[earnings_watcher] EDGAR found {len(reporters)} universe reporters ({from_date}→{to_date})")
        return reporters

    except Exception as e:
        logger.warning(f"[earnings_watcher] EDGAR lookup failed: {e}")
        return []


async def _fetch_alpha_vantage_earnings(api_key: str) -> list:
    """Alpha Vantage EARNINGS_CALENDAR — upcoming earnings, free tier."""
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

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    from_date = (today - timedelta(days=14)).strftime("%Y-%m-%d")
    to_date   = today.strftime("%Y-%m-%d")
    lookahead = today + timedelta(days=14)
    quarter   = _quarter_label(today)

    logger.info(f"[earnings_watcher] running — today={today.date()}")

    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        # Load universe candidates (skip recently analyzed)
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
            logger.info("[earnings_watcher] all stocks recently analyzed — skipping")
            return {"candidates": 0, "edgar_confirmed": 0, "newly_pending": 0, "newly_confirmed": 0}

        # ── Stage 0: EDGAR lookback — catch companies that already reported ──
        edgar_reporters = await _edgar_recent_reporters(from_date, to_date, candidates)
        edgar_confirmed = 0
        for sym, file_date in edgar_reporters:
            already = await redis_client.sismember(REDIS_KEY_QUEUE, sym)
            if not already:
                await redis_client.sadd(REDIS_KEY_QUEUE, sym)
                await redis_client.expire(REDIS_KEY_QUEUE, REDIS_TTL)
                await redis_client.hset(
                    REDIS_KEY_DETAILS, sym,
                    json.dumps({"earnings_date": file_date, "added_at": today.isoformat(), "source": "EDGAR"}),
                )
                await redis_client.expire(REDIS_KEY_DETAILS, REDIS_TTL)
                await redis_client.hdel(REDIS_KEY_PENDING, sym)
                edgar_confirmed += 1

        # ── Stage 1: Alpha Vantage upcoming → PENDING ──
        newly_pending = 0
        api_key = settings.ALPHA_VANTAGE_KEY or settings.FMP_API_KEY
        if api_key:
            try:
                earnings_data = await _fetch_alpha_vantage_earnings(api_key)
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
                    if not (today < report_date <= lookahead):
                        continue
                    # Skip if already confirmed
                    already_confirmed = await redis_client.sismember(REDIS_KEY_QUEUE, sym)
                    if already_confirmed:
                        continue
                    existing = await redis_client.hget(REDIS_KEY_PENDING, sym)
                    if not existing:
                        await redis_client.hset(
                            REDIS_KEY_PENDING, sym,
                            json.dumps({"report_date": report_date_str, "added_at": today.isoformat()}),
                        )
                        await redis_client.expire(REDIS_KEY_PENDING, REDIS_TTL)
                        newly_pending += 1
            except Exception as e:
                logger.warning(f"[earnings_watcher] Alpha Vantage failed: {e}")
        else:
            logger.warning("[earnings_watcher] No Alpha Vantage key — skipping upcoming calendar")

        # ── Stage 2: PENDING → CONFIRMED when date has passed ──
        all_pending = await redis_client.hgetall(REDIS_KEY_PENDING)
        newly_confirmed = 0
        for sym, val in all_pending.items():
            try:
                d = json.loads(val)
                report_date = datetime.strptime(d["report_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if report_date <= today:
                await redis_client.sadd(REDIS_KEY_QUEUE, sym)
                await redis_client.expire(REDIS_KEY_QUEUE, REDIS_TTL)
                await redis_client.hset(
                    REDIS_KEY_DETAILS, sym,
                    json.dumps({"earnings_date": d["report_date"], "added_at": today.isoformat(), "source": "AV"}),
                )
                await redis_client.expire(REDIS_KEY_DETAILS, REDIS_TTL)
                await redis_client.hdel(REDIS_KEY_PENDING, sym)
                newly_confirmed += 1

        queued_total  = await redis_client.scard(REDIS_KEY_QUEUE)
        pending_total = await redis_client.hlen(REDIS_KEY_PENDING)
        await redis_client.set(REDIS_KEY_LAST_CHECK, today.isoformat(), ex=REDIS_TTL)

        logger.info(
            f"[earnings_watcher] edgar={edgar_confirmed} pending={pending_total} "
            f"confirmed={queued_total}/{settings.MIN_EARNINGS_TRIGGER}"
        )

        result = {
            "candidates":      len(candidates),
            "edgar_confirmed": edgar_confirmed,
            "newly_pending":   newly_pending,
            "newly_confirmed": newly_confirmed,
            "pending_total":   int(pending_total),
            "queued_total":    int(queued_total),
            "trigger_at":      settings.MIN_EARNINGS_TRIGGER,
            "last_check":      today.isoformat(),
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
            except Exception as e:
                logger.error(f"[earnings_watcher] trigger_quarterly_scan failed: {e}")
                result["trigger_error"] = str(e)

        return result

    finally:
        await redis_client.aclose()
