"""
Celery tasks for async background processing.
All tasks are defined here and scheduled by the Beat scheduler.
"""
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import structlog

from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


def run_async(coro):
    """Helper to run async code in Celery tasks (asyncpg-safe)."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@celery_app.task(
    name="scan_asset_pool",
    queue="scanning",
    max_retries=2,
    default_retry_delay=120,
    bind=True,
)
def scan_asset_pool_task(self):
    """
    Main scanning task: runs the full 3-agent workflow on every active asset in the pool.
    Called every 5 minutes during market hours.
    """
    logger.info("scan_asset_pool_task started")

    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.db.models.asset import Asset
        from app.agents.workflow import run_investment_workflow
        from sqlalchemy import select
        import asyncio

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Asset).where(Asset.is_active_in_pool == True)
            )
            assets = result.scalars().all()

        if not assets:
            logger.warning("No assets in pool to scan")
            return {"scanned": 0, "approved": 0, "rejected": 0}

        logger.info(f"Scanning {len(assets)} assets in pool")
        approved = 0
        rejected = 0
        errors = 0

        # Process in batches to avoid overloading
        from app.core.config import settings
        batch_size = settings.MAX_CONCURRENT_SCANS

        for i in range(0, len(assets), batch_size):
            batch = assets[i:i + batch_size]
            tasks = [
                run_investment_workflow(
                    symbol=asset.symbol,
                    exchange=asset.exchange.value,
                )
                for asset in batch
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for asset, result in zip(batch, results):
                if isinstance(result, Exception):
                    import traceback
                    logger.error(
                        "Asset scan failed",
                        symbol=asset.symbol,
                        error=str(result),
                        error_type=type(result).__name__,
                        traceback=traceback.format_exc(),
                    )
                    errors += 1
                else:
                    status = result.get("workflow_status", "unknown")
                    logger.info("Asset scan result", symbol=asset.symbol, status=status)
                    if status in ("completed", "saved"):
                        approved += 1
                    elif status in ("rejected", "rejected_logged"):
                        rejected += 1
                    else:
                        logger.warning(
                            "Asset scan unexpected status",
                            symbol=asset.symbol,
                            status=status,
                            error=result.get("error"),
                        )
                        errors += 1

                # Update asset last_analyzed_at
                try:
                    from app.core.database import AsyncSessionLocal
                    from sqlalchemy import select, update
                    async with AsyncSessionLocal() as db:
                        from app.db.models.asset import Asset as AssetModel
                        db_asset = await db.get(AssetModel, asset.id)
                        if db_asset:
                            db_asset.last_analyzed_at = datetime.now(timezone.utc)
                            if not isinstance(result, Exception) and result.get("data_fetcher_output"):
                                raw = result["data_fetcher_output"]
                                db_asset.last_price = raw.get("price") or db_asset.last_price
                                db_asset.market_cap = raw.get("market_cap") or db_asset.market_cap
                                db_asset.pe_ratio = raw.get("pe_ratio") or db_asset.pe_ratio
                                if raw.get("social_sentiment"):
                                    db_asset.sentiment_score = raw["social_sentiment"].get("score", 0)
                            await db.commit()
                except Exception as e:
                    logger.warning("Failed to update asset metadata", symbol=asset.symbol, error=str(e))

        summary = {
            "scanned": len(assets),
            "approved": approved,
            "rejected": rejected,
            "errors": errors,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("scan_asset_pool_task completed", **summary)
        return summary

    try:
        return run_async(_run())
    except Exception as exc:
        logger.error("scan_asset_pool_task failed", error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(
    name="scan_user_portfolios",
    queue="scanning",
    max_retries=2,
    bind=True,
)
def scan_user_portfolios_task(self):
    """
    Scan existing holdings for sell signals.
    Checks each user's portfolio positions and triggers analysis if needed.
    """
    logger.info("scan_user_portfolios_task started")

    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.db.models.portfolio import Portfolio
        from app.db.models.user import User
        from app.agents.workflow import run_investment_workflow
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            portfolio_result = await db.execute(
                select(Portfolio, User).join(User, Portfolio.user_id == User.id).where(
                    Portfolio.quantity > 0,
                    User.is_active == True,
                    User.is_onboarded == True,
                )
            )
            holdings = portfolio_result.all()

        # Get unique symbols from all portfolios
        symbols_to_check = list({row[0].symbol for row in holdings})
        logger.info(f"Checking {len(symbols_to_check)} unique portfolio positions")

        results = {"checked": 0, "alerts_sent": 0, "errors": 0}

        for symbol in symbols_to_check:
            try:
                from app.core.database import AsyncSessionLocal
                from app.db.models.asset import Asset
                from sqlalchemy import select

                async with AsyncSessionLocal() as db:
                    asset_result = await db.execute(select(Asset).where(Asset.symbol == symbol))
                    asset = asset_result.scalar_one_or_none()

                exchange = asset.exchange.value if asset else "NASDAQ"

                workflow_result = await run_investment_workflow(
                    symbol=symbol,
                    exchange=exchange,
                )

                results["checked"] += 1

                # If recommendation is SELL/STRONG_SELL, it will have notified users already
                if workflow_result.get("senior_decision", {}).get("approved") and \
                   "SELL" in workflow_result.get("senior_decision", {}).get("final_recommendation", ""):
                    results["alerts_sent"] += 1

            except Exception as e:
                logger.error("Portfolio position scan failed", symbol=symbol, error=str(e))
                results["errors"] += 1

        logger.info("scan_user_portfolios_task completed", **results)
        return results

    try:
        return run_async(_run())
    except Exception as exc:
        logger.error("scan_user_portfolios_task failed", error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(
    name="run_technical_watchlist",
    queue="default",
    max_retries=2,
    bind=True,
)
def run_technical_watchlist_task(self, user_id: int, symbol: str, watchlist_item_id: int):
    """
    On-demand technical analysis for a watchlist item.
    Triggered when user requests technical analysis from the UI.
    """
    logger.info("run_technical_watchlist_task started", user_id=user_id, symbol=symbol)

    async def _run():
        from app.agents.workflow import run_technical_workflow
        from app.core.database import AsyncSessionLocal
        from app.db.models.asset import Asset
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            asset_result = await db.execute(select(Asset).where(Asset.symbol == symbol))
            asset = asset_result.scalar_one_or_none()
            exchange = asset.exchange.value if asset else "NASDAQ"

        result = await run_technical_workflow(
            symbol=symbol,
            exchange=exchange,
            watchlist_item_id=watchlist_item_id,
            user_id=user_id,
        )

        # If there's a strong signal, notify the user
        tech = result.get("technical_analysis") or {}
        signal = tech.get("timing_signal", "WAIT")

        if signal in ("STRONG_BUY", "STRONG_SELL", "BUY_NOW", "SELL_NOW"):
            try:
                from app.core.database import AsyncSessionLocal
                from app.services.notifications.service import get_notification_service

                notification_service = get_notification_service()
                async with AsyncSessionLocal() as db:
                    await notification_service.send_notification(
                        user_id=user_id,
                        recommendation_id=None,
                        internal_detail={
                            "type": "TECHNICAL_SIGNAL",
                            "symbol": symbol,
                            "signal": signal,
                            "technical_score": tech.get("technical_score"),
                            "rsi": tech.get("rsi_14"),
                            "signal_reasoning": tech.get("signal_reasoning"),
                        },
                        db=db,
                    )
            except Exception as e:
                logger.warning("Failed to send technical signal notification", error=str(e))

        return result

    try:
        return run_async(_run())
    except Exception as exc:
        logger.error("run_technical_watchlist_task failed", error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(
    name="update_portfolio_prices",
    queue="default",
)
def update_portfolio_prices_task():
    """
    Update current prices for all portfolio positions.
    Runs frequently to keep P&L calculations current.
    """
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.db.models.portfolio import Portfolio
        from app.db.models.user import User
        from app.db.models.asset import Asset, Exchange
        from app.services.market_data.yahoo_service import YahooFinanceService
        from app.services.market_data.tase_service import TASEService
        from app.services.order_execution.engine import get_order_execution_engine
        from sqlalchemy import select

        yahoo = YahooFinanceService()
        tase = TASEService()
        engine = get_order_execution_engine()

        async with AsyncSessionLocal() as db:
            # Get all unique held symbols
            portfolio_result = await db.execute(
                select(Portfolio.symbol, Portfolio.user_id).where(Portfolio.quantity > 0).distinct()
            )
            holdings = portfolio_result.all()

            if not holdings:
                return {"updated": 0}

            symbols = list({row[0] for row in holdings})
            prices: Dict[str, float] = {}

            # Fetch prices in batches
            for symbol in symbols:
                try:
                    asset_result = await db.execute(select(Asset).where(Asset.symbol == symbol))
                    asset = asset_result.scalar_one_or_none()

                    if asset and asset.exchange == Exchange.TASE:
                        info = await tase.get_tase_stock_info(symbol)
                    else:
                        info = await yahoo.get_stock_info(symbol)

                    price = info.get("price", 0)
                    if price > 0:
                        prices[symbol] = price

                        # Update asset's last_price too
                        if asset:
                            asset.last_price = price
                except Exception as e:
                    logger.warning("Price update failed", symbol=symbol, error=str(e))

            # Update each user's portfolio
            user_result = await db.execute(
                select(User.id).where(User.is_active == True, User.is_onboarded == True)
            )
            user_ids = [row[0] for row in user_result.all()]

            for user_id in user_ids:
                try:
                    await engine.update_portfolio_prices(user_id, prices, db)
                except Exception as e:
                    logger.warning("Portfolio price update failed", user_id=user_id, error=str(e))

            await db.commit()

        return {"updated": len(prices), "prices": prices}

    try:
        return run_async(_run())
    except Exception as exc:
        logger.error("update_portfolio_prices_task failed", error=str(exc))


@celery_app.task(
    name="cleanup_old_data",
    queue="cleanup",
)
def cleanup_old_data_task():
    """
    Housekeeping: removes old read notifications and cancelled/rejected orders.
    Runs daily.
    """
    logger.info("cleanup_old_data_task started")

    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.db.models.notification import Notification
        from app.db.models.order import Order, OrderStatus
        from app.db.models.recommendation import Recommendation, RecommendationStatus
        from sqlalchemy import select, delete
        from datetime import timedelta

        cutoff_30_days = datetime.now(timezone.utc) - timedelta(days=30)
        cutoff_90_days = datetime.now(timezone.utc) - timedelta(days=90)

        deleted_notifications = 0
        deleted_orders = 0

        async with AsyncSessionLocal() as db:
            # Delete read notifications older than 30 days
            notif_result = await db.execute(
                delete(Notification).where(
                    Notification.is_read == True,
                    Notification.sent_at < cutoff_30_days,
                )
            )
            deleted_notifications = notif_result.rowcount

            # Delete cancelled orders older than 90 days
            order_result = await db.execute(
                delete(Order).where(
                    Order.status.in_([OrderStatus.CANCELLED, OrderStatus.REJECTED]),
                    Order.created_at < cutoff_90_days,
                )
            )
            deleted_orders = order_result.rowcount

            await db.commit()

        result = {
            "deleted_notifications": deleted_notifications,
            "deleted_orders": deleted_orders,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("cleanup_old_data_task completed", **result)
        return result

    return run_async(_run())
