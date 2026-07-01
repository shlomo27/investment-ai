"""
Performance Tracking Service
Automatically tracks recommendation outcomes by comparing entry price to
current price after 30, 60, and 90-day intervals.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.db.models.recommendation import Recommendation, RecommendationStatus, RecommendationType

logger = structlog.get_logger(__name__)

OUTCOME_CHECK_DAYS = 30  # Check outcome after 30 days
WIN_THRESHOLD_PCT = 5.0  # +5% = WIN
LOSS_THRESHOLD_PCT = -5.0  # -5% = LOSS
SPY_ANNUAL_RETURN = 0.10  # S&P 500 benchmark (10% annualized)


class PerformanceService:

    async def track_pending_outcomes(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Scan all approved recommendations older than 30 days that haven't been
        outcome-tracked yet, fetch current prices, and record results.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=OUTCOME_CHECK_DAYS)

        result = await db.execute(
            select(Recommendation).where(
                and_(
                    Recommendation.status == RecommendationStatus.APPROVED,
                    Recommendation.approved_at <= cutoff,
                    Recommendation.outcome_tracked_at.is_(None),
                    Recommendation.current_price_at_recommendation.isnot(None),
                )
            )
        )
        recs = result.scalars().all()

        tracked = 0
        errors = 0

        for rec in recs:
            try:
                current_price = await self._fetch_current_price(rec.symbol)
                if current_price is None or current_price <= 0:
                    continue

                entry_price = rec.current_price_at_recommendation
                if not entry_price or entry_price <= 0:
                    continue

                return_pct = (current_price - entry_price) / entry_price * 100

                # Expected market return over the holding period (annualized SPY)
                days_held = (datetime.now(timezone.utc) - rec.approved_at).days
                market_return_pct = (SPY_ANNUAL_RETURN / 365) * days_held * 100

                vs_market = return_pct - market_return_pct

                # Determine result considering recommendation direction
                rec_type = rec.recommendation_type
                is_buy = rec_type in (RecommendationType.BUY, RecommendationType.STRONG_BUY)
                is_sell = rec_type in (RecommendationType.SELL, RecommendationType.STRONG_SELL)

                if is_buy:
                    if return_pct >= WIN_THRESHOLD_PCT:
                        outcome = "WIN"
                    elif return_pct <= LOSS_THRESHOLD_PCT:
                        outcome = "LOSS"
                    else:
                        outcome = "NEUTRAL"
                elif is_sell:
                    # For SELL: stock going down is a WIN
                    if return_pct <= LOSS_THRESHOLD_PCT:
                        outcome = "WIN"
                    elif return_pct >= WIN_THRESHOLD_PCT:
                        outcome = "LOSS"
                    else:
                        outcome = "NEUTRAL"
                else:
                    outcome = "NEUTRAL"

                rec.outcome_price = round(current_price, 4)
                rec.outcome_return_pct = round(return_pct, 2)
                rec.outcome_vs_market_pct = round(vs_market, 2)
                rec.outcome_date = datetime.now(timezone.utc)
                rec.outcome_tracked_at = datetime.now(timezone.utc)
                rec.outcome_result = outcome
                tracked += 1

            except Exception as e:
                logger.warning("Failed to track outcome", rec_id=rec.id, symbol=rec.symbol, error=str(e))
                errors += 1

        await db.flush()
        logger.info("Outcome tracking complete", tracked=tracked, errors=errors)
        return {"tracked": tracked, "errors": errors}

    async def get_performance_summary(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Returns overall recommendation performance statistics.
        """
        result = await db.execute(
            select(Recommendation).where(
                Recommendation.outcome_result.isnot(None)
            )
        )
        tracked = result.scalars().all()

        if not tracked:
            return {
                "total_tracked": 0,
                "win_count": 0,
                "loss_count": 0,
                "neutral_count": 0,
                "win_rate_pct": 0.0,
                "avg_return_pct": 0.0,
                "avg_vs_market_pct": 0.0,
                "best_trade": None,
                "worst_trade": None,
                "recent_outcomes": [],
            }

        wins = [r for r in tracked if r.outcome_result == "WIN"]
        losses = [r for r in tracked if r.outcome_result == "LOSS"]
        neutrals = [r for r in tracked if r.outcome_result == "NEUTRAL"]

        returns = [r.outcome_return_pct for r in tracked if r.outcome_return_pct is not None]
        vs_market = [r.outcome_vs_market_pct for r in tracked if r.outcome_vs_market_pct is not None]

        best = max(tracked, key=lambda r: r.outcome_return_pct or -999)
        worst = min(tracked, key=lambda r: r.outcome_return_pct or 999)

        recent = sorted(tracked, key=lambda r: r.outcome_date or datetime.min, reverse=True)[:10]

        return {
            "total_tracked": len(tracked),
            "win_count": len(wins),
            "loss_count": len(losses),
            "neutral_count": len(neutrals),
            "win_rate_pct": round(len(wins) / len(tracked) * 100, 1),
            "avg_return_pct": round(sum(returns) / len(returns), 2) if returns else 0.0,
            "avg_vs_market_pct": round(sum(vs_market) / len(vs_market), 2) if vs_market else 0.0,
            "best_trade": {
                "symbol": best.symbol,
                "return_pct": best.outcome_return_pct,
                "type": best.recommendation_type.value,
                "date": best.approved_at.isoformat() if best.approved_at else None,
            } if best else None,
            "worst_trade": {
                "symbol": worst.symbol,
                "return_pct": worst.outcome_return_pct,
                "type": worst.recommendation_type.value,
                "date": worst.approved_at.isoformat() if worst.approved_at else None,
            } if worst else None,
            "recent_outcomes": [
                {
                    "id": r.id,
                    "symbol": r.symbol,
                    "type": r.recommendation_type.value,
                    "entry_price": r.current_price_at_recommendation,
                    "outcome_price": r.outcome_price,
                    "return_pct": r.outcome_return_pct,
                    "vs_market_pct": r.outcome_vs_market_pct,
                    "result": r.outcome_result,
                    "date": r.approved_at.isoformat() if r.approved_at else None,
                }
                for r in recent
            ],
        }

    async def check_price_alerts(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """
        Check watchlist items for price alert triggers and send notifications.
        Returns list of triggered alerts.
        """
        from app.db.models.watchlist import Watchlist
        from sqlalchemy import or_

        result = await db.execute(
            select(Watchlist).where(
                or_(
                    Watchlist.alert_price_above.isnot(None),
                    Watchlist.alert_price_below.isnot(None),
                )
            )
        )
        items = result.scalars().all()

        triggered = []
        for item in items:
            try:
                current_price = await self._fetch_current_price(item.symbol)
                if current_price is None or current_price <= 0:
                    continue

                alert_fired = False
                direction = None

                if item.alert_price_above and current_price >= item.alert_price_above:
                    alert_fired = True
                    direction = "ABOVE"
                elif item.alert_price_below and current_price <= item.alert_price_below:
                    alert_fired = True
                    direction = "BELOW"

                if alert_fired:
                    item.alert_triggered_at = datetime.now(timezone.utc)
                    # Clear the alert so it doesn't re-fire
                    if direction == "ABOVE":
                        item.alert_price_above = None
                    else:
                        item.alert_price_below = None

                    triggered.append({
                        "symbol": item.symbol,
                        "user_id": item.user_id,
                        "current_price": current_price,
                        "direction": direction,
                        "watchlist_id": item.id,
                    })
            except Exception as e:
                logger.warning("Price alert check failed", symbol=item.symbol, error=str(e))

        await db.flush()
        return triggered

    @staticmethod
    async def _fetch_current_price(symbol: str) -> Optional[float]:
        """Fetch current price using the data fallback chain."""
        try:
            from app.services.market_data.yahoo_service import YahooFinanceService
            result = await YahooFinanceService().get_stock_info(symbol)
            if result and result.get("price", 0) > 0:
                return float(result["price"])
        except Exception:
            pass

        try:
            from app.services.market_data.finnhub_service import get_finnhub_service
            quote = await get_finnhub_service().get_quote(symbol)
            if quote and quote.get("c", 0) > 0:
                return float(quote["c"])
        except Exception:
            pass

        return None


_performance_service: Optional[PerformanceService] = None


def get_performance_service() -> PerformanceService:
    global _performance_service
    if _performance_service is None:
        _performance_service = PerformanceService()
    return _performance_service
