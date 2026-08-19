"""
Earnings Watcher — monitors universe stocks for fresh quarterly earnings.

Runs daily at 07:30 IL via APScheduler.

Two-source strategy:
  Past  — Nasdaq Earnings Calendar API (no key, public).
           Queries each of the last 14 days → finds companies that already reported.
  Future — Alpha Vantage EARNINGS_CALENDAR (needs key, 3-month forward).
           Adds upcoming reporters to PENDING; moves to CONFIRMED when date passes.

Trigger: when CONFIRMED ≥ MIN_EARNINGS_TRIGGER → quarterly scan.

Redis keys:
  investment_ai:earnings_pending      HASH   — sym → {report_date, added_at}
  investment_ai:earnings_queue        SET    — confirmed reporters
  investment_ai:earnings_details      HASH   — sym → {earnings_date, added_at, source}
  investment_ai:earnings_last_check   STRING — ISO timestamp of last run
  investment_ai:earnings_scan_triggered STRING — quarter when triggered
"""
import asyncio
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

NASDAQ_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}


def _quarter_label(dt: datetime) -> str:
    return f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"


async def _finnhub_reporters(from_date: str, to_date: str, universe: set) -> dict:
    """symbol -> report date for companies that ALREADY reported (epsActual is
    populated) in the window, filtered to the universe. Second detection source
    alongside Nasdaq."""
    from app.services.market_data.earnings_calendar_service import get_earnings_calendar_service
    svc = get_earnings_calendar_service()
    if not getattr(svc, "_enabled", False):
        return {}
    import httpx as _httpx
    from app.core.config import settings as _settings
    out = {}
    try:
        async with _httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://finnhub.io/api/v1/calendar/earnings",
                params={"from": from_date, "to": to_date, "token": _settings.FINNHUB_API_KEY},
            )
            if resp.status_code != 200:
                return {}
            for item in resp.json().get("earningsCalendar", []):
                sym = (item.get("symbol") or "").upper()
                # epsActual present => the company has actually reported
                if sym in universe and item.get("epsActual") is not None:
                    out[sym] = item.get("date", "")
    except Exception:
        return out
    return out


async def _analyze_reporters_now(syms: list) -> int:
    """Run a full analysis on each freshly-reported company immediately (used
    when no quarterly sweep will cover it). Budget-guarded — stops at the daily
    cap; the rest are picked up by the next quarterly trigger."""
    from app.workers.cost_guard import (
        budget_exceeded, record_analysis_cost, is_decision_engine_down,
        is_engine_down_result, mark_decision_engine_down, clear_decision_engine_down,
    )
    from app.agents.workflow import run_investment_workflow
    from app.core.database import AsyncSessionLocal
    from app.db.models.asset import Asset
    from sqlalchemy import select as _sel

    if await is_decision_engine_down():
        logger.warning("[earnings_watcher] immediate analysis skipped — decision engine DOWN")
        return 0

    analyzed = 0
    for sym in syms:
        try:
            if await budget_exceeded():
                logger.warning("[earnings_watcher] immediate analysis halted — daily budget")
                break
            async with AsyncSessionLocal() as db:
                asset = (await db.execute(_sel(Asset).where(Asset.symbol == sym))).scalar_one_or_none()
            if not asset:
                continue  # not in the tracked universe
            result = await run_investment_workflow(
                symbol=sym, exchange=asset.exchange.value,
                trigger_type="EARNINGS", trigger_details="immediate earnings analysis",
            )
            if is_engine_down_result(result):
                # Engine down — stop before producing more 0.0 rejections.
                await mark_decision_engine_down()
                logger.error("[earnings_watcher] immediate analysis halted — engine DOWN")
                break
            await clear_decision_engine_down()
            await record_analysis_cost(1)
            analyzed += 1
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"[earnings_watcher] immediate analysis {sym} failed: {e}")
    if analyzed:
        logger.info(f"[earnings_watcher] immediate-analyzed {analyzed} fresh reporters")
    return analyzed


async def _requeue_for_rescan(redis_client, sym: str) -> None:
    """A company reported earnings — if a quarterly scan is ACTIVE, re-analyze
    it with the fresh data even if it was already scanned this sweep: drop it
    from the done set and push it to the FRONT of the todo queue. Tracks a
    counter so the completion report can mention re-scans."""
    QP = "investment_ai:quarterly_scan:"
    try:
        if not await redis_client.get(QP + "active"):
            return  # no active sweep — it'll be picked up by the next trigger
        removed = await redis_client.srem(QP + "done", sym)
        # Only requeue if it isn't already waiting in todo.
        pending = set(await redis_client.lrange(QP + "todo", 0, -1))
        pending = {p.decode() if isinstance(p, bytes) else p for p in pending}
        if sym not in pending:
            await redis_client.rpush(QP + "todo", sym)  # rpush → tail → rpop next
            await redis_client.incr(QP + "rescans")
            import logging as _l
            _l.getLogger(__name__).info(f"[earnings_watcher] requeued {sym} for re-scan (fresh earnings)")
    except Exception:
        pass


async def _nasdaq_reporters_for_date(date_str: str, universe: set) -> list:
    """
    Fetch companies that reported earnings on a specific date from Nasdaq.
    Returns list of symbols found in our universe.
    """
    url = f"https://api.nasdaq.com/api/calendar/earnings"
    params = {"date": date_str}
    try:
        async with httpx.AsyncClient(timeout=15, headers=NASDAQ_HEADERS) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return []
            data = resp.json()
        rows = (data.get("data") or {}).get("rows") or []
        found = []
        for row in rows:
            sym = (row.get("symbol") or "").upper().strip()
            if sym and sym in universe:
                found.append(sym)
        return found
    except Exception as e:
        logger.debug(f"[earnings_watcher] Nasdaq {date_str}: {e}")
        return []


async def _fetch_alpha_vantage_earnings(api_key: str) -> list:
    """Alpha Vantage EARNINGS_CALENDAR — upcoming earnings (free tier)."""
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
    lookahead = today + timedelta(days=14)
    quarter   = _quarter_label(today)

    logger.info(f"[earnings_watcher] running — today={today.date()}")

    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        # Load universe candidates (skip recently analyzed in last 70 days)
        cutoff_analyzed = today - timedelta(days=70)
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(Asset.symbol, Asset.last_analyzed_at).where(Asset.in_universe == True)
            )
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
            return {"candidates": 0, "past_confirmed": 0, "newly_pending": 0}

        # ── Past reporters: Nasdaq calendar for last 14 days ──────────────────
        past_confirmed = 0
        newly_syms: set = set()
        for days_back in range(1, 15):
            check_date = today - timedelta(days=days_back)
            # Skip weekends (markets closed)
            if check_date.weekday() >= 5:
                continue
            date_str = check_date.strftime("%Y-%m-%d")
            reporters = await _nasdaq_reporters_for_date(date_str, candidates)
            for sym in reporters:
                already = await redis_client.sismember(REDIS_KEY_QUEUE, sym)
                if not already:
                    await redis_client.sadd(REDIS_KEY_QUEUE, sym)
                    await redis_client.expire(REDIS_KEY_QUEUE, REDIS_TTL)
                    await redis_client.hset(
                        REDIS_KEY_DETAILS, sym,
                        json.dumps({"earnings_date": date_str, "added_at": today.isoformat(), "source": "Nasdaq"}),
                    )
                    await redis_client.expire(REDIS_KEY_DETAILS, REDIS_TTL)
                    await redis_client.hdel(REDIS_KEY_PENDING, sym)
                    past_confirmed += 1
                    newly_syms.add(sym)
                    await _requeue_for_rescan(redis_client, sym)

        logger.info(f"[earnings_watcher] Nasdaq past lookback: {past_confirmed} new confirmed")

        # ── Second source: Finnhub earnings calendar (past 14 days) ───────────
        # Nasdaq's feed has gaps (it missed IBM). Finnhub cross-checks so a
        # reporter detected by EITHER source is caught.
        try:
            fh_reporters = await _finnhub_reporters(
                (today - timedelta(days=14)).strftime("%Y-%m-%d"),
                today.strftime("%Y-%m-%d"),
                set(universe_map.keys()),
            )
            fh_new = 0
            for sym, ed in fh_reporters.items():
                if not await redis_client.sismember(REDIS_KEY_QUEUE, sym):
                    await redis_client.sadd(REDIS_KEY_QUEUE, sym)
                    await redis_client.expire(REDIS_KEY_QUEUE, REDIS_TTL)
                    await redis_client.hset(
                        REDIS_KEY_DETAILS, sym,
                        json.dumps({"earnings_date": ed, "added_at": today.isoformat(), "source": "Finnhub"}),
                    )
                    await redis_client.expire(REDIS_KEY_DETAILS, REDIS_TTL)
                    await redis_client.hdel(REDIS_KEY_PENDING, sym)
                    past_confirmed += 1
                    newly_syms.add(sym)
                    await _requeue_for_rescan(redis_client, sym)
                    fh_new += 1
            logger.info(f"[earnings_watcher] Finnhub cross-check: {fh_new} additional reporters")
        except Exception as e:
            logger.warning(f"[earnings_watcher] Finnhub source failed: {e}")

        # ── Upcoming reporters: Alpha Vantage → PENDING ───────────────────────
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

        # ── Move pending whose date passed → CONFIRMED ────────────────────────
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
                newly_syms.add(sym)
                await _requeue_for_rescan(redis_client, sym)

        queued_total  = await redis_client.scard(REDIS_KEY_QUEUE)
        pending_total = await redis_client.hlen(REDIS_KEY_PENDING)
        await redis_client.set(REDIS_KEY_LAST_CHECK, today.isoformat(), ex=REDIS_TTL)

        logger.info(
            f"[earnings_watcher] confirmed={queued_total}/{settings.MIN_EARNINGS_TRIGGER} | pending={pending_total}"
        )

        result = {
            "candidates":       len(candidates),
            "past_confirmed":   past_confirmed,
            "newly_pending":    newly_pending,
            "newly_confirmed":  newly_confirmed,
            "queued_total":     int(queued_total),
            "pending_total":    int(pending_total),
            "trigger_at":       settings.MIN_EARNINGS_TRIGGER,
            "last_check":       today.isoformat(),
        }

        # PRIMARY engine: analyze every fresh reporter immediately (no more
        # waiting for a 20-report threshold). If a full sweep is already
        # running, those symbols were re-queued for it instead — skip to avoid
        # double work.
        scan_active = await redis_client.get("investment_ai:quarterly_scan:active")
        if newly_syms and not scan_active:
            result["immediate_analyzed"] = await _analyze_reporters_now(list(newly_syms))

        # SAFETY NET: a full-universe sweep still runs periodically to catch
        # anything both earnings sources missed (feed gaps) and non-reporters.
        # Time-based now (not the 20-earnings trigger) — fire if none has
        # completed in ~80 days and no sweep is currently active.
        try:
            last_sweep = await redis_client.get("investment_ai:quarterly_scan:last_completed")
            due = True
            if last_sweep:
                try:
                    last_dt = datetime.fromisoformat(last_sweep.decode() if isinstance(last_sweep, bytes) else last_sweep)
                    due = (today - last_dt.replace(tzinfo=timezone.utc)).days >= 80
                except Exception:
                    due = True
            if due and not scan_active:
                logger.info("[earnings_watcher] safety-net sweep due → triggering full scan")
                scan_result = await trigger_quarterly_scan(quarter)
                result["safety_net_sweep"] = scan_result
                await redis_client.set(REDIS_KEY_TRIGGERED, quarter, ex=REDIS_TTL)
        except Exception as e:
            logger.warning(f"[earnings_watcher] safety-net sweep check failed: {e}")

        return result

    finally:
        await redis_client.aclose()
