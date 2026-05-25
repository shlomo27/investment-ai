"""
Portfolio API routes
GET /portfolio, GET /portfolio/summary, GET /portfolio/{symbol}, POST /portfolio/settings
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_active_user
from app.db.models.user import User
from app.db.models.portfolio import Portfolio
from app.db.models.asset import Asset
from app.services.order_execution.engine import get_order_execution_engine
from app.services.risk.manager import get_risk_manager

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


class PortfolioPositionResponse(BaseModel):
    id: int
    symbol: str
    quantity: float
    avg_buy_price: float
    current_price: float
    current_value: float
    pnl: float
    pnl_percentage: float
    exposure_percentage: float
    asset_name: Optional[str] = None
    sector: Optional[str] = None
    risk_level: Optional[str] = None
    updated_at: datetime

    class Config:
        from_attributes = True


class PortfolioSummaryResponse(BaseModel):
    total_value: float
    cash_balance: float
    total_market_value: float
    total_cost_basis: float
    total_pnl: float
    total_pnl_pct: float
    position_count: int
    risk_score: Optional[int]
    risk_level: Optional[str]
    positions: List[PortfolioPositionResponse]


class ExposureSettingsRequest(BaseModel):
    max_single_asset_exposure_pct: float = Field(ge=0.5, le=25.0)


@router.get("/", response_model=List[PortfolioPositionResponse])
async def get_portfolio(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all portfolio positions for the current user."""
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.user_id == current_user.id,
            Portfolio.quantity > 0,
        )
    )
    positions = result.scalars().all()

    # Enrich with asset data
    symbols = [p.symbol for p in positions]
    assets_result = await db.execute(select(Asset).where(Asset.symbol.in_(symbols)))
    assets = {a.symbol: a for a in assets_result.scalars().all()}

    response = []
    for pos in positions:
        asset = assets.get(pos.symbol)
        response.append(PortfolioPositionResponse(
            id=pos.id,
            symbol=pos.symbol,
            quantity=pos.quantity,
            avg_buy_price=pos.avg_buy_price,
            current_price=pos.current_price,
            current_value=pos.current_value,
            pnl=pos.pnl,
            pnl_percentage=pos.pnl_percentage,
            exposure_percentage=pos.exposure_percentage,
            asset_name=asset.name if asset else None,
            sector=asset.sector if asset else None,
            risk_level=asset.risk_level.value if asset else None,
            updated_at=pos.updated_at,
        ))

    return response


@router.get("/summary", response_model=PortfolioSummaryResponse)
async def get_portfolio_summary(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get portfolio summary with P&L and risk metrics."""
    engine = get_order_execution_engine()
    risk_manager = get_risk_manager()

    summary = await engine.get_portfolio_summary(current_user.id, db)
    risk = await risk_manager.calculate_portfolio_risk(current_user.id, db)

    positions_result = await db.execute(
        select(Portfolio).where(
            Portfolio.user_id == current_user.id,
            Portfolio.quantity > 0,
        )
    )
    positions = positions_result.scalars().all()

    symbols = [p.symbol for p in positions]
    assets_result = await db.execute(select(Asset).where(Asset.symbol.in_(symbols)))
    assets = {a.symbol: a for a in assets_result.scalars().all()}

    enriched_positions = []
    for pos in positions:
        asset = assets.get(pos.symbol)
        enriched_positions.append(PortfolioPositionResponse(
            id=pos.id,
            symbol=pos.symbol,
            quantity=pos.quantity,
            avg_buy_price=pos.avg_buy_price,
            current_price=pos.current_price,
            current_value=pos.current_value,
            pnl=pos.pnl,
            pnl_percentage=pos.pnl_percentage,
            exposure_percentage=pos.exposure_percentage,
            asset_name=asset.name if asset else None,
            sector=asset.sector if asset else None,
            risk_level=asset.risk_level.value if asset else None,
            updated_at=pos.updated_at,
        ))

    return PortfolioSummaryResponse(
        total_value=summary.get("total_value", 0),
        cash_balance=current_user.cash_balance,
        total_market_value=summary.get("total_market_value", 0),
        total_cost_basis=summary.get("total_cost_basis", 0),
        total_pnl=summary.get("total_pnl", 0),
        total_pnl_pct=summary.get("total_pnl_pct", 0),
        position_count=len(positions),
        risk_score=risk.get("risk_score"),
        risk_level=risk.get("risk_level"),
        positions=enriched_positions,
    )


@router.get("/risk", response_model=Dict[str, Any])
async def get_portfolio_risk(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed portfolio risk analysis."""
    risk_manager = get_risk_manager()
    return await risk_manager.calculate_portfolio_risk(current_user.id, db)


@router.get("/rebalancing", response_model=List[Dict[str, Any]])
async def get_rebalancing_suggestions(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get AI-generated rebalancing suggestions for the portfolio."""
    risk_manager = get_risk_manager()
    return await risk_manager.suggest_rebalancing(current_user.id, db)


@router.post("/settings")
async def update_portfolio_settings(
    request: ExposureSettingsRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update portfolio risk settings (exposure limits)."""
    risk_manager = get_risk_manager()
    success = await risk_manager.apply_exposure_limit(
        current_user.id,
        request.max_single_asset_exposure_pct,
        db,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update settings",
        )

    return {
        "message": "Settings updated successfully",
        "max_single_asset_exposure_pct": request.max_single_asset_exposure_pct,
    }


@router.get("/{asset_symbol}", response_model=Optional[PortfolioPositionResponse])
async def get_asset_position(
    asset_symbol: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get portfolio position for a specific asset."""
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.user_id == current_user.id,
            Portfolio.symbol == asset_symbol.upper(),
        )
    )
    position = result.scalar_one_or_none()

    if not position:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No position found for {asset_symbol}",
        )

    asset_result = await db.execute(select(Asset).where(Asset.symbol == asset_symbol.upper()))
    asset = asset_result.scalar_one_or_none()

    return PortfolioPositionResponse(
        id=position.id,
        symbol=position.symbol,
        quantity=position.quantity,
        avg_buy_price=position.avg_buy_price,
        current_price=position.current_price,
        current_value=position.current_value,
        pnl=position.pnl,
        pnl_percentage=position.pnl_percentage,
        exposure_percentage=position.exposure_percentage,
        asset_name=asset.name if asset else None,
        sector=asset.sector if asset else None,
        risk_level=asset.risk_level.value if asset else None,
        updated_at=position.updated_at,
    )
