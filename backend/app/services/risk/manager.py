"""
Risk Management Service
Handles portfolio risk calculation, exposure checks, and rebalancing suggestions.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.db.models.user import User
from app.db.models.portfolio import Portfolio
from app.db.models.asset import Asset

logger = structlog.get_logger(__name__)


class RiskManager:
    """
    Portfolio risk management engine.
    Calculates risk metrics, exposure checks, and rebalancing suggestions.
    """

    async def check_exposure(
        self,
        user_id: int,
        symbol: str,
        amount: float,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """
        Check if adding an amount to a position would violate exposure limits.
        Returns dict with allowed, warning, blocked, and message.
        """
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        if not user:
            return {
                "allowed": False, "warning": False, "blocked": True,
                "message": "User not found", "current_exposure_pct": 0.0,
                "max_allowed_pct": 0.0,
            }

        portfolio_result = await db.execute(
            select(Portfolio).where(Portfolio.user_id == user_id, Portfolio.quantity > 0)
        )
        positions = portfolio_result.scalars().all()

        total_market_value = sum(p.current_value for p in positions)
        total_value = total_market_value + user.cash_balance

        if total_value <= 0:
            return {
                "allowed": True, "warning": False, "blocked": False,
                "message": "Cannot calculate exposure - no portfolio value",
                "current_exposure_pct": 0.0,
                "max_allowed_pct": user.max_single_asset_exposure * 100,
            }

        # Find existing position
        existing_value = 0.0
        for pos in positions:
            if pos.symbol == symbol:
                existing_value = pos.current_value
                break

        projected_value = existing_value + amount
        projected_exposure_pct = (projected_value / total_value) * 100
        max_allowed_pct = user.max_single_asset_exposure * 100

        if projected_exposure_pct > max_allowed_pct * 2.0:
            return {
                "allowed": False, "warning": False, "blocked": True,
                "current_exposure_pct": projected_exposure_pct,
                "max_allowed_pct": max_allowed_pct,
                "existing_value": existing_value,
                "projected_value": projected_value,
                "total_portfolio_value": total_value,
                "message": (
                    f"BLOCKED: Would result in {projected_exposure_pct:.1f}% exposure "
                    f"to {symbol} (max {max_allowed_pct:.1f}%)"
                ),
            }
        elif projected_exposure_pct > max_allowed_pct:
            return {
                "allowed": True, "warning": True, "blocked": False,
                "current_exposure_pct": projected_exposure_pct,
                "max_allowed_pct": max_allowed_pct,
                "existing_value": existing_value,
                "projected_value": projected_value,
                "total_portfolio_value": total_value,
                "message": (
                    f"WARNING: {symbol} exposure at {projected_exposure_pct:.1f}% "
                    f"exceeds recommended {max_allowed_pct:.1f}%"
                ),
            }
        else:
            return {
                "allowed": True, "warning": False, "blocked": False,
                "current_exposure_pct": projected_exposure_pct,
                "max_allowed_pct": max_allowed_pct,
                "existing_value": existing_value,
                "projected_value": projected_value,
                "total_portfolio_value": total_value,
                "message": "Exposure within allowed limits",
            }

    async def calculate_portfolio_risk(
        self, user_id: int, db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Calculate overall portfolio risk metrics.
        Returns comprehensive risk assessment dict.
        """
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        if not user:
            return {}

        portfolio_result = await db.execute(
            select(Portfolio).where(Portfolio.user_id == user_id, Portfolio.quantity > 0)
        )
        positions = portfolio_result.scalars().all()

        if not positions:
            return {
                "user_id": user_id,
                "risk_score": 0,
                "risk_level": "NONE",
                "total_positions": 0,
                "diversification_score": 100,
                "message": "No positions - portfolio is all cash",
            }

        total_market_value = sum(p.current_value for p in positions)
        total_value = total_market_value + user.cash_balance

        # Concentration risk: Herfindahl-Hirschman Index
        if total_value > 0:
            weights = [p.current_value / total_value for p in positions]
            hhi = sum(w ** 2 for w in weights) * 10000  # 0-10000
        else:
            hhi = 0

        # Check for overconcentrated positions
        overconcentrated = [
            p.symbol for p in positions
            if total_value > 0 and (p.current_value / total_value) > user.max_single_asset_exposure
        ]

        # Load asset risk levels
        symbols = [p.symbol for p in positions]
        assets_result = await db.execute(
            select(Asset).where(Asset.symbol.in_(symbols))
        )
        assets = {a.symbol: a for a in assets_result.scalars().all()}

        risk_breakdown = []
        for pos in positions:
            asset = assets.get(pos.symbol)
            risk_level = asset.risk_level.value if asset else "MEDIUM"
            exposure_pct = (pos.current_value / total_value * 100) if total_value > 0 else 0

            risk_breakdown.append({
                "symbol": pos.symbol,
                "exposure_pct": round(exposure_pct, 2),
                "risk_level": risk_level,
                "pnl_pct": round(pos.pnl_percentage, 2),
                "current_value": round(pos.current_value, 2),
            })

        # Portfolio risk score (0-100)
        high_risk_exposure = sum(
            rb["exposure_pct"] for rb in risk_breakdown
            if rb["risk_level"] in ("HIGH", "VERY_HIGH")
        )
        medium_risk_exposure = sum(
            rb["exposure_pct"] for rb in risk_breakdown
            if rb["risk_level"] == "MEDIUM"
        )

        risk_score = min(100, int(high_risk_exposure * 1.0 + medium_risk_exposure * 0.5 + hhi / 200))
        cash_pct = (user.cash_balance / total_value * 100) if total_value > 0 else 100
        diversification_score = max(0, 100 - int(hhi / 100))

        if risk_score >= 70:
            risk_level = "HIGH"
        elif risk_score >= 40:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        return {
            "user_id": user_id,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "total_value": round(total_value, 2),
            "total_market_value": round(total_market_value, 2),
            "cash_balance": round(user.cash_balance, 2),
            "cash_pct": round(cash_pct, 2),
            "total_positions": len(positions),
            "herfindahl_index": round(hhi, 2),
            "diversification_score": diversification_score,
            "high_risk_exposure_pct": round(high_risk_exposure, 2),
            "medium_risk_exposure_pct": round(medium_risk_exposure, 2),
            "overconcentrated_positions": overconcentrated,
            "risk_breakdown": risk_breakdown,
            "user_risk_profile": user.risk_profile.value,
            "user_risk_score": user.risk_score,
            "max_single_asset_pct": user.max_single_asset_exposure * 100,
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def suggest_rebalancing(
        self, user_id: int, db: AsyncSession
    ) -> List[Dict[str, Any]]:
        """
        Generate rebalancing suggestions based on current portfolio risk.
        Returns list of actionable suggestions.
        """
        risk_data = await self.calculate_portfolio_risk(user_id, db)

        if not risk_data:
            return []

        suggestions: List[Dict[str, Any]] = []
        max_single_pct = risk_data.get("max_single_asset_pct", 3.0)

        # Check for overconcentrated positions
        for pos_risk in risk_data.get("risk_breakdown", []):
            if pos_risk["exposure_pct"] > max_single_pct:
                excess_pct = pos_risk["exposure_pct"] - max_single_pct
                suggestions.append({
                    "type": "REDUCE_POSITION",
                    "symbol": pos_risk["symbol"],
                    "priority": "HIGH" if excess_pct > max_single_pct else "MEDIUM",
                    "current_exposure_pct": pos_risk["exposure_pct"],
                    "target_exposure_pct": max_single_pct,
                    "excess_pct": round(excess_pct, 2),
                    "message": (
                        f"Reduce {pos_risk['symbol']} from {pos_risk['exposure_pct']:.1f}% "
                        f"to {max_single_pct:.1f}% - currently overweight"
                    ),
                    "action": "SELL",
                })

        # Suggest increasing cash position if risk is high
        if risk_data.get("risk_score", 0) > 70 and risk_data.get("cash_pct", 100) < 10:
            suggestions.append({
                "type": "INCREASE_CASH",
                "priority": "HIGH",
                "current_cash_pct": risk_data.get("cash_pct"),
                "target_cash_pct": 15.0,
                "message": "Portfolio risk is HIGH - consider liquidating some positions to increase cash buffer",
                "action": "SELL",
            })

        # Suggest diversification if HHI is too high
        if risk_data.get("herfindahl_index", 0) > 2500:
            suggestions.append({
                "type": "DIVERSIFY",
                "priority": "MEDIUM",
                "current_hhi": risk_data.get("herfindahl_index"),
                "diversification_score": risk_data.get("diversification_score"),
                "message": "Portfolio is overly concentrated - consider adding more diverse positions",
                "action": "BUY",
            })

        return suggestions

    async def apply_exposure_limit(
        self,
        user_id: int,
        limit_pct: float,
        db: AsyncSession,
    ) -> bool:
        """Update a user's maximum single-asset exposure limit."""
        try:
            user_result = await db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()
            if not user:
                return False

            # Clamp to reasonable range (0.5% to 25%)
            limit_pct = max(0.5, min(25.0, limit_pct))
            user.max_single_asset_exposure = limit_pct / 100.0
            await db.flush()

            logger.info("Exposure limit updated", user_id=user_id, new_limit_pct=limit_pct)
            return True

        except Exception as e:
            logger.error("apply_exposure_limit failed", user_id=user_id, error=str(e))
            return False


_risk_manager: Optional[RiskManager] = None


def get_risk_manager() -> RiskManager:
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager()
    return _risk_manager
