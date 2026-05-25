"""
Market Data API routes
GET /market/search, GET /market/asset/{symbol}, GET /market/tase/search, GET /market/pool
"""
from typing import Any, Dict, List, Optional
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_active_user
from app.db.models.user import User
from app.db.models.asset import Asset, Exchange, AssetType, RiskLevel
from app.services.market_data.yahoo_service import YahooFinanceService
from app.services.market_data.tase_service import TASEService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/market", tags=["Market Data"])


class AssetPoolResponse(BaseModel):
    id: int
    symbol: str
    name: str
    exchange: str
    asset_type: str
    risk_level: str
    sector: Optional[str]
    country: str
    last_price: Optional[float]
    market_cap: Optional[float]
    pe_ratio: Optional[float]
    sentiment_score: float
    fundamental_score: float
    is_active_in_pool: bool

    class Config:
        from_attributes = True


@router.get("/search")
async def search_market(
    q: str = Query(min_length=1),
    exchange: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Search for stocks globally (Yahoo Finance)."""
    yahoo = YahooFinanceService()
    results = await yahoo.search_stocks(q)

    # Also search our asset pool
    pool_query = select(Asset).where(
        Asset.symbol.ilike(f"%{q}%") | Asset.name.ilike(f"%{q}%")
    ).limit(10)
    pool_result = await db.execute(pool_query)
    pool_assets = pool_result.scalars().all()

    pool_symbols = {a.symbol for a in pool_assets}

    # Merge results
    for asset in pool_assets:
        if asset.symbol not in {r.get("symbol") for r in results}:
            results.insert(0, {
                "symbol": asset.symbol,
                "name": asset.name,
                "exchange": asset.exchange.value,
                "type": asset.asset_type.value,
                "currency": "ILS" if asset.exchange == Exchange.TASE else "USD",
                "in_pool": True,
            })

    for r in results:
        r["in_pool"] = r.get("symbol") in pool_symbols

    return results[:20]


@router.get("/tase/search")
async def search_tase(
    q: str = Query(min_length=1),
    current_user: User = Depends(get_current_active_user),
):
    """Search Israeli stocks on TASE."""
    tase = TASEService()
    results = await tase.search_tase(q)
    return results


@router.get("/pool", response_model=List[AssetPoolResponse])
async def get_asset_pool(
    active_only: bool = True,
    exchange: Optional[str] = None,
    risk_level: Optional[str] = None,
    sector: Optional[str] = None,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the active asset pool being scanned by AI agents."""
    query = select(Asset)

    if active_only:
        query = query.where(Asset.is_active_in_pool == True)

    if exchange:
        try:
            exchange_enum = Exchange(exchange.upper())
            query = query.where(Asset.exchange == exchange_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid exchange: {exchange}",
            )

    if risk_level:
        try:
            risk_enum = RiskLevel(risk_level.upper())
            query = query.where(Asset.risk_level == risk_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid risk level: {risk_level}",
            )

    if sector:
        query = query.where(Asset.sector.ilike(f"%{sector}%"))

    query = query.limit(limit)
    result = await db.execute(query)
    assets = result.scalars().all()

    return [
        AssetPoolResponse(
            id=a.id,
            symbol=a.symbol,
            name=a.name,
            exchange=a.exchange.value,
            asset_type=a.asset_type.value,
            risk_level=a.risk_level.value,
            sector=a.sector,
            country=a.country,
            last_price=a.last_price,
            market_cap=a.market_cap,
            pe_ratio=a.pe_ratio,
            sentiment_score=a.sentiment_score,
            fundamental_score=a.fundamental_score,
            is_active_in_pool=a.is_active_in_pool,
        )
        for a in assets
    ]


@router.get("/asset/{symbol}")
async def get_asset_data(
    symbol: str,
    include_sentiment: bool = True,
    include_technical: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get comprehensive real-time data for a specific asset.
    Fetches from Yahoo Finance or TASE based on the asset's exchange.
    """
    symbol = symbol.upper()

    # Check our DB first
    asset_result = await db.execute(select(Asset).where(Asset.symbol == symbol))
    asset = asset_result.scalar_one_or_none()

    is_tase = asset and asset.exchange == Exchange.TASE

    try:
        if is_tase:
            tase = TASEService()
            data = await tase.get_tase_stock_info(symbol)
        else:
            yahoo = YahooFinanceService()
            data = await yahoo.get_stock_info(symbol)

        if not data or data.get("price", 0) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No data found for symbol {symbol}",
            )

        result = {
            "symbol": symbol,
            "exchange": "TASE" if is_tase else data.get("exchange", "NASDAQ"),
            "data": data,
            "in_pool": asset is not None and asset.is_active_in_pool,
            "pool_data": {
                "fundamental_score": asset.fundamental_score if asset else None,
                "sentiment_score": asset.sentiment_score if asset else None,
                "risk_level": asset.risk_level.value if asset else None,
                "last_analyzed_at": asset.last_analyzed_at.isoformat() if asset and asset.last_analyzed_at else None,
            } if asset else None,
        }

        if include_technical and not is_tase:
            from app.agents.workflow import run_technical_workflow
            tech = await run_technical_workflow(symbol, data.get("exchange", "NASDAQ"))
            result["technical_analysis"] = tech.get("technical_analysis")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_asset_data failed", symbol=symbol, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch data for {symbol}: {str(e)}",
        )


@router.post("/pool/add")
async def add_to_pool(
    symbol: str,
    exchange: str = "NASDAQ",
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a new asset to the scanning pool (admin action)."""
    symbol = symbol.upper()

    existing = await db.execute(select(Asset).where(Asset.symbol == symbol))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{symbol} is already in the pool",
        )

    try:
        exchange_enum = Exchange(exchange.upper())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid exchange: {exchange}")

    # Fetch basic info
    try:
        if exchange_enum == Exchange.TASE:
            tase = TASEService()
            info = await tase.get_tase_stock_info(symbol)
        else:
            yahoo = YahooFinanceService()
            info = await yahoo.get_stock_info(symbol)
    except Exception:
        info = {}

    asset = Asset(
        symbol=symbol,
        name=info.get("name", symbol),
        exchange=exchange_enum,
        asset_type=AssetType.STOCK,
        is_active_in_pool=True,
        risk_level=RiskLevel.MEDIUM,
        sector=info.get("sector"),
        country=info.get("country", "US"),
        last_price=info.get("price"),
        market_cap=info.get("market_cap"),
        pe_ratio=info.get("pe_ratio"),
    )
    db.add(asset)
    await db.flush()

    return {"message": f"{symbol} added to pool", "asset_id": asset.id}
