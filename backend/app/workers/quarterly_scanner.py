"""
Quarterly Scanner — full universe scan triggered by earnings releases.

Flow:
  1. earnings_watcher detects ≥ MIN_EARNINGS_TRIGGER stocks with fresh earnings
     → calls trigger_quarterly_scan(quarter)
  2. trigger_quarterly_scan loads all ~900 in_universe stocks into a Redis queue
  3. job_quarterly_scan_batch() runs daily and processes BATCH_PER_DAY stocks
     using the full Claude 3-agent workflow (fetch → fundamental → senior)
  4. When the queue is empty → notifies admin to review and publish Master List

The scan deliberately spans multiple days (≈ 18 days for 900 stocks at 50/day)
which matches the natural pace of an earnings season.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import List

logger = logging.getLogger(__name__)

# Redis keys (all get the same TTL so they expire together after the season)
_TODO_KEY    = "investment_ai:quarterly_scan:todo"     # set of symbols still to scan
_DONE_KEY    = "investment_ai:quarterly_scan:done"     # set of symbols already scanned
_QUARTER_KEY = "investment_ai:quarterly_scan:quarter"  # e.g. "Q1-2026"
_ACTIVE_KEY  = "investment_ai:quarterly_scan:active"   # "1" while scan is in progress
_TTL         = 86400 * 60                              # 60 days

BATCH_PER_DAY = 50   # stocks processed per daily job run


async def trigger_quarterly_scan(quarter: str) -> bool:
    """
    Initialize the quarterly scan queue with all universe stocks.
    Called by earnings_watcher when the earnings trigger fires.
    Returns True if scan was started, False if one is already running.
    """
    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.db.models.asset import Asset
    from sqlalchemy import select
    import redis.asyncio as aioredis

    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        # Guard: don't start a second scan if one is already running
        already_active = await redis_client.get(_ACTIVE_KEY)
        if already_active:
            logger.info(f"[quarterly_scanner] Scan already in progress for quarter {await redis_client.get(_QUARTER_KEY)} — skipping")
            return False

        # Load all universe symbols
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(Asset.symbol).where(Asset.in_universe == True)
            )
            symbols = [r[0] for r in rows.all()]

        logger.info(f"[quarterly_scanner] Initialising quarterly scan: {len(symbols)} stocks, quarter={quarter}")

        # Populate the todo queue
        if symbols:
            await redis_client.sadd(_TODO_KEY, *symbols)
            await redis_client.expire(_TODO_KEY, _TTL)

        await redis_client.set(_ACTIVE_KEY, "1", ex=_TTL)
        await redis_client.set(_QUARTER_KEY, quarter, ex=_TTL)
        await redis_client.delete(_DONE_KEY)  # clear previous done set

        logger.info(f"[quarterly_scanner] Queue ready: {len(symbols)} symbols — daily batch job will process {BATCH_PER_DAY}/day")
        return True

    finally:
        await redis_client.aclose()


async def job_quarterly_scan_batch():
    """
    Daily APScheduler entry point.
    Pops the next BATCH_PER_DAY symbols from the Redis queue and runs
    the full Claude fundamental workflow on each one.
    When the queue is empty, notifies the admin.
    """
    from app.core.config import settings
    import redis.asyncio as aioredis

    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        active = await redis_client.get(_ACTIVE_KEY)
        if not active:
            return  # no quarterly scan in progress

        quarter = (await redis_client.get(_QUARTER_KEY) or b"").decode()

        # Pop next batch (SRANDMEMBER doesn't remove; we remove manually)
        raw = await redis_client.srandmember(_TODO_KEY, BATCH_PER_DAY)
        if not raw:
            # Queue empty — scan complete
            await _on_scan_complete(redis_client, quarter)
            return

        batch = [s.decode() if isinstance(s, bytes) else s for s in raw]
        todo_remaining = await redis_client.scard(_TODO_KEY)
        done_count = await redis_client.scard(_DONE_KEY)

        logger.info(
            f"[quarterly_scanner] Processing batch of {len(batch)} stocks "
            f"(done={done_count}, remaining={todo_remaining}, quarter={quarter})"
        )

        await _scan_batch(batch, quarter, redis_client)

    finally:
        await redis_client.aclose()


async def _scan_batch(symbols: List[str], quarter: str, redis_client) -> None:
    """Run full Claude workflow for a batch of symbols and update Redis progress."""
    from app.core.database import AsyncSessionLocal
    from app.db.models.asset import Asset
    from app.agents.workflow import run_investment_workflow
    from sqlalchemy import select

    # Fetch exchange + direction_bias for this batch
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(Asset.symbol, Asset.exchange, Asset.direction_bias)
            .where(Asset.symbol.in_(symbols))
        )
        asset_map = {r[0]: (r[1], r[2]) for r in rows.all()}

    approved = rejected = errors = 0
    PARALLEL = 3  # simultaneous Claude calls

    for i in range(0, len(symbols), PARALLEL):
        chunk = symbols[i: i + PARALLEL]
        results = await asyncio.gather(
            *[
                run_investment_workflow(
                    symbol=sym,
                    exchange=asset_map[sym][0].value if sym in asset_map else "NASDAQ",
                    direction_bias=asset_map[sym][1] if sym in asset_map else "NEUTRAL",
                    trigger_type="QUARTERLY",
                    trigger_details=f"Quarterly earnings scan {quarter}",
                    language="he",
                )
                for sym in chunk
            ],
            return_exceptions=True,
        )
        for sym, r in zip(chunk, results):
            # Move symbol from todo → done regardless of outcome
            await redis_client.srem(_TODO_KEY, sym)
            await redis_client.sadd(_DONE_KEY, sym)
            await redis_client.expire(_DONE_KEY, 86400 * 60)

            if isinstance(r, Exception):
                errors += 1
                logger.warning(f"[quarterly_scanner] {sym} error: {r}")
            elif isinstance(r, dict):
                if r.get("workflow_status") in ("completed", "saved"):
                    approved += 1
                else:
                    rejected += 1

        await asyncio.sleep(2)

    logger.info(
        f"[quarterly_scanner] Batch done: "
        f"approved={approved}, rejected={rejected}, errors={errors}"
    )

    # Check if queue is now empty
    remaining = await redis_client.scard(_TODO_KEY)
    if remaining == 0:
        await _on_scan_complete(redis_client, quarter)


async def _on_scan_complete(redis_client, quarter: str) -> None:
    """Called when all universe stocks have been scanned. Notifies admin."""
    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.db.models.user import User
    from app.db.models.notification import NotificationType
    from app.services.notifications.service import NotificationService
    from sqlalchemy import select

    total_done = await redis_client.scard(_DONE_KEY)
    logger.info(
        f"[quarterly_scanner] *** Quarterly scan COMPLETE *** "
        f"quarter={quarter}, total={total_done}"
    )

    # Clear active flag so next season can start fresh
    await redis_client.delete(_ACTIVE_KEY)

    # Notify all admin users
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User).where(User.is_active == True, User.is_admin == True)
            )
            admins = result.scalars().all()

            if not admins:
                # Fallback: notify all active users
                result = await db.execute(select(User).where(User.is_active == True))
                admins = result.scalars().all()

            svc = NotificationService()
            for admin in admins:
                await svc.send_notification(
                    user_id=admin.id,
                    recommendation_id=None,
                    internal_detail={
                        "quarter": quarter,
                        "total_scanned": total_done,
                        "action": "publish_master_list",
                    },
                    db=db,
                    notification_type=NotificationType.SYSTEM,
                    title=(
                        f"✅ הסריקה הרבעונית {quarter} הושלמה — {total_done} מניות נסרקו. "
                        f"כנס ל-Fund Dashboard לאישור ופרסום המאסטר ליסט."
                    ),
                )
    except Exception as e:
        logger.error(f"[quarterly_scanner] Failed to notify admin: {e}")


async def get_quarterly_scan_status() -> dict:
    """Returns current quarterly scan progress (for dashboard endpoint)."""
    from app.core.config import settings
    import redis.asyncio as aioredis

    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        active  = bool(await redis_client.get(_ACTIVE_KEY))
        quarter = (await redis_client.get(_QUARTER_KEY) or b"").decode()
        todo    = await redis_client.scard(_TODO_KEY)
        done    = await redis_client.scard(_DONE_KEY)
        total   = todo + done
        pct     = round(done / total * 100) if total else 0

        return {
            "active": active,
            "quarter": quarter,
            "total": total,
            "done": done,
            "remaining": todo,
            "progress_pct": pct,
        }
    finally:
        await redis_client.aclose()
