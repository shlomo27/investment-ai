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

    live_data: Optional[Dict[str, Any]] = None
    live_error: Optional[str] = None

    try:
        if is_tase:
            tase = TASEService()
            live_data = await tase.get_tase_stock_info(symbol)
        else:
            yahoo = YahooFinanceService()
            live_data = await yahoo.get_stock_info(symbol)

        if not live_data or live_data.get("price", 0) == 0:
            live_data = None
            live_error = "Live price unavailable"
    except Exception as e:
        live_error = str(e)
        logger.warning("Live data fetch failed", symbol=symbol, error=live_error)

    # Fall back to DB-cached data when live feed is down
    if live_data is None:
        if asset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Symbol {symbol} not found in pool and live data unavailable",
            )
        # Build a partial response from what we have in the DB
        live_data = {
            "price": asset.last_price or 0.0,
            "previous_close": asset.last_price or 0.0,
            "volume": 0,
            "market_cap": asset.market_cap or 0.0,
            "pe_ratio": asset.pe_ratio,
            "name": asset.name,
            "sector": asset.sector,
            "country": asset.country,
            "currency": "ILS" if asset.exchange == Exchange.TASE else "USD",
            "exchange": asset.exchange.value,
        }

    result = {
        "symbol": symbol,
        "exchange": "TASE" if is_tase else live_data.get("exchange", "NASDAQ"),
        "data": live_data,
        "live_data": live_error is None,
        "live_error": live_error,
        "in_pool": asset is not None and asset.is_active_in_pool,
        "pool_data": {
            "fundamental_score": asset.fundamental_score if asset else None,
            "sentiment_score": asset.sentiment_score if asset else None,
            "risk_level": asset.risk_level.value if asset else None,
            "last_analyzed_at": asset.last_analyzed_at.isoformat() if asset and asset.last_analyzed_at else None,
        } if asset else None,
    }

    if include_technical and not is_tase and live_error is None:
        try:
            from app.agents.workflow import run_technical_workflow
            tech = await run_technical_workflow(symbol, live_data.get("exchange", "NASDAQ"))
            result["technical_analysis"] = tech.get("technical_analysis")
        except Exception as te:
            logger.warning("Technical analysis failed", symbol=symbol, error=str(te))

    return result


class AddToPoolRequest(BaseModel):
    symbol: str
    exchange: str = "NASDAQ"


@router.post("/pool/add")
async def add_to_pool(
    body: Optional[AddToPoolRequest] = None,
    symbol: Optional[str] = None,
    exchange: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a new asset to the scanning pool (admin action).

    Accepts either a JSON body ``{"symbol": "AAPL", "exchange": "NASDAQ"}``
    or legacy query params ``?symbol=AAPL&exchange=NASDAQ``.
    """
    # Resolve symbol / exchange from body or query params
    resolved_symbol: str = (body.symbol if body else None) or symbol or ""
    resolved_exchange: str = (body.exchange if body else None) or exchange or "NASDAQ"

    if not resolved_symbol:
        from fastapi import HTTPException as _HTTPException
        raise _HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="symbol is required (provide via JSON body or query param)",
        )

    symbol = resolved_symbol.upper()

    existing = await db.execute(select(Asset).where(Asset.symbol == symbol))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{symbol} is already in the pool",
        )

    try:
        exchange_enum = Exchange(resolved_exchange.upper())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid exchange: {resolved_exchange}")

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


@router.post("/pool/seed")
async def seed_pool(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Seed the asset pool with curated stocks."""
    from app.db.seed import seed_asset_pool
    result = await seed_asset_pool(db)
    return result


@router.post("/universe/load")
async def load_universe_endpoint(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Load S&P 500 + S&P 400 constituents into the universe (admin action)."""
    from app.workers.universe_loader import load_universe
    result = await load_universe(db)
    return result


@router.post("/universe/screen")
async def run_screener_endpoint(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Run the pre-screener now: scores universe, activates top LONG/SHORT candidates."""
    from app.workers.pre_screener import run_pre_screener
    result = await run_pre_screener(db)
    return result


@router.get("/universe/stats")
async def universe_stats(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Return universe size, active pool counts, and top-scored candidates."""
    from sqlalchemy import func as sqlfunc
    from app.db.models.asset import Asset

    total_universe = await db.execute(
        select(sqlfunc.count(Asset.id)).where(Asset.in_universe == True)
    )
    active_long = await db.execute(
        select(sqlfunc.count(Asset.id)).where(
            Asset.is_active_in_pool == True, Asset.direction_bias == "LONG"
        )
    )
    active_short = await db.execute(
        select(sqlfunc.count(Asset.id)).where(
            Asset.is_active_in_pool == True, Asset.direction_bias == "SHORT"
        )
    )
    seeded = await db.execute(
        select(sqlfunc.count(Asset.id)).where(Asset.in_universe == False)
    )

    top_long_result = await db.execute(
        select(Asset.symbol, Asset.long_score, Asset.direction_bias)
        .where(Asset.in_universe == True)
        .order_by(Asset.long_score.desc())
        .limit(10)
    )
    top_short_result = await db.execute(
        select(Asset.symbol, Asset.short_score, Asset.direction_bias)
        .where(Asset.in_universe == True)
        .order_by(Asset.short_score.desc())
        .limit(10)
    )

    return {
        "universe_total": total_universe.scalar(),
        "seeded_pool": seeded.scalar(),
        "active_long": active_long.scalar(),
        "active_short": active_short.scalar(),
        "top_long": [
            {"symbol": r[0], "long_score": r[1], "direction": r[2]}
            for r in top_long_result.fetchall()
        ],
        "top_short": [
            {"symbol": r[0], "short_score": r[1], "direction": r[2]}
            for r in top_short_result.fetchall()
        ],
    }
