"""
Quarterly Scanner — manages the full-universe quarterly scan lifecycle.

Redis keys (60-day TTL):
  investment_ai:quarterly_scan:todo    — list of symbols to scan
  investment_ai:quarterly_scan:done    — set of scanned symbols
  investment_ai:quarterly_scan:quarter — e.g. "2025-Q2"
  investment_ai:quarterly_scan:active  — "1" while scan is running
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

REDIS_PREFIX  = "investment_ai:quarterly_scan:"
BATCH_PER_DAY = 50
TTL_SECONDS   = 60 * 24 * 3600  # 60 days


async def _earnings_report_dates(redis_client) -> dict:
    """symbol -> earnings report date (YYYY-MM-DD) from the earnings tracker,
    used to order freshly-reported companies oldest-report-first."""
    import json as _json
    out = {}
    try:
        details = await redis_client.hgetall("investment_ai:earnings_details")
        for k, v in details.items():
            sym = k.decode() if isinstance(k, bytes) else k
            try:
                d = _json.loads(v.decode() if isinstance(v, bytes) else v)
                if d.get("earnings_date"):
                    out[sym] = d["earnings_date"]
            except Exception:
                continue
    except Exception:
        pass
    return out


def _order_priority(priority, date_map):
    """Oldest-reported first; reporters with no known date go last in the group."""
    return sorted(priority, key=lambda s: date_map.get(s, "9999-99-99"))


async def trigger_quarterly_scan(quarter: str) -> dict:
    """Load ALL universe stocks into the Redis scan queue. Guards against double-start."""
    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.db.models.asset import Asset
    from sqlalchemy import select
    import redis.asyncio as aioredis

    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        active = await redis_client.get(REDIS_PREFIX + "active")
        if active:
            existing = (await redis_client.get(REDIS_PREFIX + "quarter") or b"").decode()
            logger.info(f"[quarterly_scanner] already active for {existing} — skipping")
            return {"started": False, "total": 0, "quarter": existing}

        async with AsyncSessionLocal() as db:
            rows = await db.execute(select(Asset.symbol))
            symbols = [r[0] for r in rows.all()]

        if not symbols:
            return {"started": False, "total": 0, "quarter": quarter}

        # Freshly-reported companies (the ones that TRIGGERED this scan) go to
        # the FRONT — their 10-Q data is newest, so analyze them while it's
        # fresh instead of weeks later when the alphabetical cursor arrives.
        reported = {s.decode() for s in await redis_client.smembers("investment_ai:earnings_queue")}
        date_map = await _earnings_report_dates(redis_client)
        priority = _order_priority([s for s in symbols if s in reported], date_map)
        rest = [s for s in symbols if s not in reported]
        ordered = priority + rest  # lpush in consumption order → rpop returns priority first (oldest report first)

        pipe = redis_client.pipeline()
        pipe.delete(REDIS_PREFIX + "todo")
        pipe.delete(REDIS_PREFIX + "done")
        for sym in ordered:
            pipe.lpush(REDIS_PREFIX + "todo", sym)
        pipe.set(REDIS_PREFIX + "quarter", quarter, ex=TTL_SECONDS)
        pipe.set(REDIS_PREFIX + "active", "1", ex=TTL_SECONDS)
        await pipe.execute()

        logger.info(
            f"[quarterly_scanner] triggered {quarter} — {len(symbols)} queued "
            f"({len(priority)} freshly-reported prioritized)"
        )
        return {"started": True, "total": len(symbols), "quarter": quarter,
                "prioritized": len(priority)}
    finally:
        await redis_client.aclose()


async def reprioritize_todo_with_earnings() -> dict:
    """Reorder the EXISTING scan queue so freshly-reported companies are next.
    Used when a scan was already triggered before earnings prioritization —
    rebuilds the todo list with reporters at the front (safe while the batch
    is not actively popping)."""
    from app.core.config import settings
    import redis.asyncio as aioredis

    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        pending = [s.decode() for s in await redis_client.lrange(REDIS_PREFIX + "todo", 0, -1)]
        if not pending:
            return {"reordered": False, "reason": "queue empty"}
        reported = {s.decode() for s in await redis_client.smembers("investment_ai:earnings_queue")}
        date_map = await _earnings_report_dates(redis_client)
        priority = _order_priority([s for s in pending if s in reported], date_map)
        rest = [s for s in pending if s not in reported]
        if not priority:
            return {"reordered": False, "reason": "no reported companies pending", "pending": len(pending)}
        ordered = priority + rest
        pipe = redis_client.pipeline()
        pipe.delete(REDIS_PREFIX + "todo")
        for sym in ordered:
            pipe.lpush(REDIS_PREFIX + "todo", sym)
        await pipe.execute()
        logger.info(f"[quarterly_scanner] reprioritized queue — {len(priority)} reporters moved to front")
        return {"reordered": True, "prioritized": len(priority), "pending": len(pending)}
    finally:
        await redis_client.aclose()


async def get_quarterly_scan_status() -> dict:
    from app.core.config import settings
    import redis.asyncio as aioredis
    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        active  = await redis_client.get(REDIS_PREFIX + "active")
        quarter = (await redis_client.get(REDIS_PREFIX + "quarter") or b"").decode()
        todo    = await redis_client.llen(REDIS_PREFIX + "todo")
        done    = await redis_client.scard(REDIS_PREFIX + "done")
        total   = todo + done
        return {
            "active":       bool(active),
            "quarter":      quarter,
            "total":        total,
            "done":         done,
            "remaining":    todo,
            "progress_pct": round(done/total*100, 1) if total else 0,
        }
    finally:
        await redis_client.aclose()


async def _on_scan_complete(quarter: str) -> None:
    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.db.models.user import User
    from app.db.models.notification import NotificationType
    from app.services.notifications.service import NotificationService
    from sqlalchemy import select
    import redis.asyncio as aioredis

    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        scanned  = await redis_client.scard(REDIS_PREFIX + "done")
        rescans  = int(await redis_client.get(REDIS_PREFIX + "rescans") or 0)
        await redis_client.delete(REDIS_PREFIX + "active")
        await redis_client.delete(REDIS_PREFIX + "rescans")
        # Stamp completion so the earnings watcher knows when the last full
        # safety-net sweep finished (drives the ~80-day timer).
        from datetime import datetime as _dt, timezone as _tz
        await redis_client.set(REDIS_PREFIX + "last_completed", _dt.now(_tz.utc).isoformat(), ex=TTL_SECONDS)
    finally:
        await redis_client.aclose()

    rescan_note = f" (כולל {rescans} ניתוחים חוזרים על חברות שדיווחו תוך כדי)" if rescans else ""
    title = (
        f"✅ הסריקה הרבעונית ל-{quarter} הסתיימה — נסרקו {scanned} מניות{rescan_note}. "
        f"בחן תוצאות ופרסם רשימת מאסטר."
    )

    # Admin Telegram channel — this is the milestone the admin waits for.
    try:
        from app.services.notifications.telegram_service import get_telegram_service
        await get_telegram_service().send_admin_alert(
            f"✅ <b>הסריקה הרבעונית הושלמה — {quarter}</b>\n\n"
            f"נסרקו כל {scanned} המניות ביקום{rescan_note}.\n\n"
            f"רשימת מאסטר ← \"פרסם רשימה חדשה\" לתיעוד רשמי מעודכן."
        )
    except Exception as e:
        logger.warning(f"[quarterly_scanner] completion telegram failed: {e}")

    notifier = NotificationService()
    async with AsyncSessionLocal() as db:
        rows = await db.execute(select(User.id).where(User.is_admin == True))
        admin_ids = [r[0] for r in rows.all()]
        for uid in admin_ids:
            await notifier.send_notification(
                user_id=uid, recommendation_id=None,
                internal_detail={"type": "QUARTERLY_SCAN_COMPLETE", "quarter": quarter,
                                 "scanned": scanned, "rescans": rescans},
                db=db, notification_type=NotificationType.SYSTEM,
                title=title,
            )
    logger.info(f"[quarterly_scanner] scan complete for {quarter} — scanned={scanned}, rescans={rescans}")


async def job_quarterly_scan_batch() -> dict:
    """APScheduler entry point — runs daily at 12:00. Pops 50 symbols/day."""
    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.db.models.asset import Asset
    from app.agents.workflow import run_investment_workflow
    from sqlalchemy import select
    import redis.asyncio as aioredis

    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        active = await redis_client.get(REDIS_PREFIX + "active")
        if not active:
            logger.debug("[quarterly_scanner] no active scan — skipping")
            return {"skipped": True}

        quarter = (await redis_client.get(REDIS_PREFIX + "quarter") or b"").decode()
        logger.info(f"[quarterly_scanner] batch for {quarter}")

        # Bump freshly-reported companies to the front every run (oldest report
        # first), so the automatic scan prioritizes them without the admin
        # having to press "resume".
        try:
            pending = [s.decode() for s in await redis_client.lrange(REDIS_PREFIX + "todo", 0, -1)]
            reported = {s.decode() for s in await redis_client.smembers("investment_ai:earnings_queue")}
            prio = _order_priority([s for s in pending if s in reported],
                                   await _earnings_report_dates(redis_client))
            if prio:
                rest = [s for s in pending if s not in reported]
                pipe = redis_client.pipeline()
                pipe.delete(REDIS_PREFIX + "todo")
                for sym in (prio + rest):
                    pipe.lpush(REDIS_PREFIX + "todo", sym)
                await pipe.execute()
                logger.info(f"[quarterly_scanner] batch reprioritized {len(prio)} reporters to front")
        except Exception as e:
            logger.warning(f"[quarterly_scanner] batch reprioritize failed: {e}")

        from app.workers.cost_guard import budget_exceeded, record_analysis_cost, get_today_spend

        approved = rejected = errors = 0
        processed = []

        for _ in range(BATCH_PER_DAY):
            if await budget_exceeded():
                spend = await get_today_spend()
                logger.warning(f"[quarterly_scanner] halted — daily budget hit (~${spend:.2f})")
                from app.services.notifications.telegram_service import get_telegram_service
                await get_telegram_service().send_admin_alert(
                    f"💰 <b>עצירת תקציב</b>\nהסריקה הרבעונית נעצרה להיום — תקרת הוצאה (~${spend:.2f})."
                )
                break
            sym_bytes = await redis_client.rpop(REDIS_PREFIX + "todo")
            if not sym_bytes:
                break
            symbol = sym_bytes.decode()
            try:
                async with AsyncSessionLocal() as db:
                    asset = (await db.execute(select(Asset).where(Asset.symbol==symbol))).scalar_one_or_none()
                exchange       = asset.exchange.value if asset else "NASDAQ"
                direction_bias = getattr(asset, "direction_bias", None)
                result = await run_investment_workflow(symbol=symbol, exchange=exchange, direction_bias=direction_bias)
                status = (result or {}).get("workflow_status", "")
                if status in ("completed", "saved"):
                    approved += 1
                else:
                    rejected += 1
            except Exception as exc:
                errors += 1
                logger.warning(f"[quarterly_scanner] {symbol}: {exc}")
            await record_analysis_cost(1)
            # Heartbeat: keep the running-flag alive per symbol so a killed
            # batch (deploy/restart) unblocks the manual resume button within
            # ~10 minutes instead of a stale 4h lock.
            await redis_client.set(REDIS_PREFIX + "batch_running", "1", ex=600)
            await redis_client.sadd(REDIS_PREFIX + "done", symbol)
            await redis_client.expire(REDIS_PREFIX + "done", TTL_SECONDS)
            processed.append(symbol)
            await asyncio.sleep(1)

        remaining = await redis_client.llen(REDIS_PREFIX + "todo")
        result = {"quarter": quarter, "processed": len(processed),
                  "approved": approved, "rejected": rejected, "errors": errors, "remaining": remaining}
        logger.info(f"[quarterly_scanner] batch done: {result}")

        if remaining == 0:
            await _on_scan_complete(quarter)

        if approved:
            from app.workers.in_process_scheduler import maybe_nudge_master_list_publish
            await maybe_nudge_master_list_publish()

        return result
    finally:
        await redis_client.aclose()
