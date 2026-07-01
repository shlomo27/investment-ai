"""
Performance Tracking API
GET /performance/summary — overall recommendation performance stats
GET /performance/history — list of tracked recommendations with outcomes
GET /performance/comparison — AI vs S&P 500 cumulative return chart
GET /performance/timeline — monthly win rate breakdown
GET /performance/portfolio-history — daily portfolio value snapshots
POST /performance/track-now — manually trigger outcome tracking (admin)
POST /performance/snapshot-now — manually trigger portfolio snapshot (admin)
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_db
from app.core.security import get_current_active_user
from app.db.models.user import User
from app.db.models.recommendation import Recommendation, RecommendationStatus
from app.services.performance_service import get_performance_service

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/performance", tags=["Performance"])


@router.get("/summary")
async def get_performance_summary(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Return aggregated recommendation performance statistics."""
    return await get_performance_service().get_performance_summary(db)


@router.get("/history")
async def get_performance_history(
    limit: int = 50,
    offset: int = 0,
    outcome_only: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List all tracked recommendations with their outcomes."""
    from sqlalchemy import desc

    query = select(Recommendation).where(
        Recommendation.status == RecommendationStatus.APPROVED
    )
    if outcome_only:
        query = query.where(Recommendation.outcome_result.isnot(None))

    query = query.order_by(desc(Recommendation.approved_at)).limit(limit).offset(offset)
    result = await db.execute(query)
    recs = result.scalars().all()

    return [
        {
            "id": r.id,
            "symbol": r.symbol,
            "type": r.recommendation_type.value,
            "confidence_score": r.confidence_score,
            "entry_price": r.current_price_at_recommendation,
            "target_price": r.target_price,
            "stop_loss": r.stop_loss,
            "expected_return_pct": r.expected_return_pct,
            "outcome_price": r.outcome_price,
            "outcome_return_pct": r.outcome_return_pct,
            "outcome_vs_market_pct": r.outcome_vs_market_pct,
            "outcome_result": r.outcome_result,
            "outcome_date": r.outcome_date.isoformat() if r.outcome_date else None,
            "approved_at": r.approved_at.isoformat() if r.approved_at else None,
            # Scenario analysis from fundamental_analysis JSON
            "scenario_analysis": (r.fundamental_analysis or {}).get("scenario_analysis"),
            "allocation_recommendation": (r.fundamental_analysis or {}).get("allocation_recommendation"),
            "moat_classification": (r.fundamental_analysis or {}).get("moat_classification"),
        }
        for r in recs
    ]


@router.get("/comparison")
async def get_comparison_chart(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """AI recommendations vs S&P 500 cumulative return comparison chart data."""
    return await get_performance_service().get_comparison_chart(db)


@router.get("/timeline")
async def get_performance_timeline(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Monthly performance breakdown: win rate, avg return, vs market."""
    return await get_performance_service().get_performance_timeline(db)


@router.get("/portfolio-history")
async def get_portfolio_history(
    days: int = 90,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Daily portfolio value snapshots for the current user (last N days)."""
    from app.db.models.portfolio_history import PortfolioHistory
    from sqlalchemy import desc

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(PortfolioHistory)
        .where(
            and_(
                PortfolioHistory.user_id == current_user.id,
                PortfolioHistory.snapshot_date >= cutoff,
            )
        )
        .order_by(PortfolioHistory.snapshot_date)
    )
    rows = result.scalars().all()
    return [
        {
            "date": r.snapshot_date.strftime("%Y-%m-%d"),
            "total_value": r.total_value,
            "cash_balance": r.cash_balance,
            "market_value": r.market_value,
            "total_pnl": r.total_pnl,
            "total_pnl_pct": r.total_pnl_pct,
        }
        for r in rows
    ]


@router.post("/snapshot-now")
async def take_portfolio_snapshot(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Admin: manually trigger a portfolio snapshot for all users."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    result = await get_performance_service().take_portfolio_snapshot(db)
    await db.commit()
    return result


@router.get("/backtest")
async def run_backtest(
    initial_capital: float = 100000.0,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Simulate equal-weight portfolio performance across all tracked recommendations."""
    return await get_performance_service().run_backtest(db, initial_capital=initial_capital)


@router.post("/track-now")
async def trigger_outcome_tracking(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Manually trigger recommendation outcome tracking (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return await get_performance_service().track_pending_outcomes(db)
