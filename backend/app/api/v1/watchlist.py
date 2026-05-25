"""
Watchlist API routes
GET /watchlist, POST /watchlist, DELETE /watchlist/{id}, POST /watchlist/{id}/technical-analysis
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_active_user
from app.db.models.user import User
from app.db.models.watchlist import Watchlist
from app.db.models.asset import Asset, Exchange

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/watchlist", tags=["Watchlist"])


class AddToWatchlistRequest(BaseModel):
    symbol: str
    exchange: str = "NASDAQ"
    alert_on_technical_signal: bool = True
    notes: Optional[str] = None


class WatchlistItemResponse(BaseModel):
    id: int
    symbol: str
    asset_id: Optional[int]
    alert_on_technical_signal: bool
    last_technical_analysis: Optional[Dict[str, Any]]
    last_signal_sent_at: Optional[datetime]
    notes: Optional[str]
    created_at: datetime
    asset_name: Optional[str] = None
    asset_risk_level: Optional[str] = None
    current_price: Optional[float] = None
    technical_signal: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/", response_model=List[WatchlistItemResponse])
async def get_watchlist(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all watchlist items for the current user."""
    result = await db.execute(
        select(Watchlist).where(Watchlist.user_id == current_user.id)
    )
    items = result.scalars().all()

    # Enrich with asset data
    symbols = [item.symbol for item in items]
    assets_result = await db.execute(select(Asset).where(Asset.symbol.in_(symbols)))
    assets = {a.symbol: a for a in assets_result.scalars().all()}

    response = []
    for item in items:
        asset = assets.get(item.symbol)
        tech = item.last_technical_analysis or {}
        response.append(WatchlistItemResponse(
            id=item.id,
            symbol=item.symbol,
            asset_id=item.asset_id,
            alert_on_technical_signal=item.alert_on_technical_signal,
            last_technical_analysis=item.last_technical_analysis,
            last_signal_sent_at=item.last_signal_sent_at,
            notes=item.notes,
            created_at=item.created_at,
            asset_name=asset.name if asset else None,
            asset_risk_level=asset.risk_level.value if asset else None,
            current_price=asset.last_price if asset else tech.get("current_price"),
            technical_signal=tech.get("timing_signal"),
        ))

    return response


@router.post("/", response_model=WatchlistItemResponse, status_code=status.HTTP_201_CREATED)
async def add_to_watchlist(
    request: AddToWatchlistRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a symbol to the user's watchlist."""
    symbol = request.symbol.upper()

    # Check if already in watchlist
    existing_result = await db.execute(
        select(Watchlist).where(
            Watchlist.user_id == current_user.id,
            Watchlist.symbol == symbol,
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{symbol} is already in your watchlist",
        )

    # Try to find or create asset record
    asset_result = await db.execute(select(Asset).where(Asset.symbol == symbol))
    asset = asset_result.scalar_one_or_none()

    if not asset:
        try:
            exchange_enum = Exchange(request.exchange.upper())
        except ValueError:
            exchange_enum = Exchange.NASDAQ

        # Fetch basic info to create asset record
        if exchange_enum == Exchange.TASE:
            from app.services.market_data.tase_service import TASEService
            svc = TASEService()
            info = await svc.get_tase_stock_info(symbol)
        else:
            from app.services.market_data.yahoo_service import YahooFinanceService
            svc = YahooFinanceService()
            info = await svc.get_stock_info(symbol)

        from app.db.models.asset import AssetType, RiskLevel
        asset = Asset(
            symbol=symbol,
            name=info.get("name", symbol),
            exchange=exchange_enum,
            asset_type=AssetType.STOCK,
            is_active_in_pool=False,
            risk_level=RiskLevel.MEDIUM,
            sector=info.get("sector"),
            country=info.get("country", "US"),
            last_price=info.get("price"),
        )
        db.add(asset)
        await db.flush()

    watchlist_item = Watchlist(
        user_id=current_user.id,
        symbol=symbol,
        asset_id=asset.id if asset else None,
        alert_on_technical_signal=request.alert_on_technical_signal,
        notes=request.notes,
    )
    db.add(watchlist_item)
    await db.flush()

    return WatchlistItemResponse(
        id=watchlist_item.id,
        symbol=watchlist_item.symbol,
        asset_id=watchlist_item.asset_id,
        alert_on_technical_signal=watchlist_item.alert_on_technical_signal,
        last_technical_analysis=None,
        last_signal_sent_at=None,
        notes=watchlist_item.notes,
        created_at=watchlist_item.created_at,
        asset_name=asset.name if asset else None,
        asset_risk_level=asset.risk_level.value if asset else None,
        current_price=asset.last_price if asset else None,
        technical_signal=None,
    )


@router.delete("/{watchlist_id}")
async def remove_from_watchlist(
    watchlist_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a symbol from the user's watchlist."""
    result = await db.execute(
        select(Watchlist).where(
            Watchlist.id == watchlist_id,
            Watchlist.user_id == current_user.id,
        )
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist item not found")

    await db.delete(item)

    return {"message": f"Removed {item.symbol} from watchlist", "id": watchlist_id}


@router.post("/{watchlist_id}/technical-analysis")
async def run_technical_analysis(
    watchlist_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger on-demand technical analysis for a watchlist item.
    Runs the TechnicalAnalystAgent and returns results immediately.
    """
    result = await db.execute(
        select(Watchlist).where(
            Watchlist.id == watchlist_id,
            Watchlist.user_id == current_user.id,
        )
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist item not found")

    # Get exchange from asset
    exchange = "NASDAQ"
    if item.asset_id:
        asset_result = await db.execute(select(Asset).where(Asset.id == item.asset_id))
        asset = asset_result.scalar_one_or_none()
        if asset:
            exchange = asset.exchange.value

    from app.agents.workflow import run_technical_workflow
    technical_result = await run_technical_workflow(
        symbol=item.symbol,
        exchange=exchange,
        watchlist_item_id=watchlist_id,
        user_id=current_user.id,
    )

    tech_analysis = technical_result.get("technical_analysis")

    if tech_analysis:
        item.last_technical_analysis = tech_analysis
        item.last_signal_sent_at = datetime.now(timezone.utc)
        await db.flush()

    return {
        "watchlist_id": watchlist_id,
        "symbol": item.symbol,
        "technical_analysis": tech_analysis,
        "workflow_status": technical_result.get("workflow_status"),
        "error": technical_result.get("error"),
    }


@router.put("/{watchlist_id}/settings")
async def update_watchlist_settings(
    watchlist_id: int,
    alert_on_technical_signal: bool,
    notes: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update settings for a watchlist item."""
    result = await db.execute(
        select(Watchlist).where(
            Watchlist.id == watchlist_id,
            Watchlist.user_id == current_user.id,
        )
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist item not found")

    item.alert_on_technical_signal = alert_on_technical_signal
    if notes is not None:
        item.notes = notes
    await db.flush()

    return {"message": "Watchlist settings updated", "id": watchlist_id}
