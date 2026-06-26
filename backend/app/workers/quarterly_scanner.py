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

        pipe = redis_client.pipeline()
        pipe.delete(REDIS_PREFIX + "todo")
        pipe.delete(REDIS_PREFIX + "done")
        for sym in symbols:
            pipe.lpush(REDIS_PREFIX + "todo", sym)
        pipe.set(REDIS_PREFIX + "quarter", quarter, ex=TTL_SECONDS)
        pipe.set(REDIS_PREFIX + "active", "1", ex=TTL_SECONDS)
        await pipe.execute()

        logger.info(f"[quarterly_scanner] triggered {quarter} — {len(symbols)} symbols queued")
        return {"started": True, "total": len(symbols), "quarter": quarter}
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
        await redis_client.delete(REDIS_PREFIX + "active")
    finally:
        await redis_client.aclose()

    notifier = NotificationService()
    async with AsyncSessionLocal() as db:
        rows = await db.execute(select(User.id).where(User.is_admin == True))
        admin_ids = [r[0] for r in rows.all()]
        for uid in admin_ids:
            await notifier.send_notification(
                user_id=uid, recommendation_id=None,
                internal_detail={"type": "QUARTERLY_SCAN_COMPLETE", "quarter": quarter},
                db=db, notification_type=NotificationType.SYSTEM,
                title=f"✅ הסריקה הרבעונית ל-{quarter} הסתיימה — בחן תוצאות ופרסם רשימת מאסטר",
            )
    logger.info(f"[quarterly_scanner] scan complete for {quarter} — {len(admin_ids)} admins notified")


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

        approved = rejected = errors = 0
        processed = []

        for _ in range(BATCH_PER_DAY):
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

        return result
    finally:
        await redis_client.aclose()
