"""
Market Data API routes
GET /market/search, GET /market/asset/{symbol}, GET /market/tase/search, GET /market/pool
"""
from datetime import datetime, timezone
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


# ─── Redis-backed scan state ──────────────────────────────────────────────────
# Railway runs 4 uvicorn workers (separate processes). An in-process dict is
# NOT shared across workers — the POST and GET would hit different workers and
# the status would always read as 0. Redis is shared, so all workers see the
# same state.

import json as _json

_SCAN_KEY = "investment_ai:scan_state"
_SCAN_DEFAULT: dict = {
    "running": False, "total": 0, "scanned": 0, "approved": 0,
    "rejected": 0, "errors": 0, "symbols_done": [],
    "started_at": None, "finished_at": None, "error": None,
}


async def _scan_state_get() -> dict:
    try:
        import redis.asyncio as aioredis
        from app.core.config import settings
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        data = await r.get(_SCAN_KEY)
        await r.aclose()
        return _json.loads(data) if data else dict(_SCAN_DEFAULT)
    except Exception:
        return dict(_SCAN_DEFAULT)


async def _scan_state_set(state: dict) -> None:
    try:
        import redis.asyncio as aioredis
        from app.core.config import settings
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await r.set(_SCAN_KEY, _json.dumps(state), ex=7200)
        await r.aclose()
    except Exception:
        pass


async def _run_scan_background(symbols_with_meta: list[dict]) -> None:
    """Background task: scan stocks 3 at a time, update Redis state as we go."""
    import asyncio as _aio
    from app.agents.workflow import run_investment_workflow
    from app.core.database import AsyncSessionLocal
    from app.db.models.asset import Asset as AssetModel
    from sqlalchemy import update as sa_update

    state = await _scan_state_get()
    state.update({
        "running": True, "scanned": 0, "approved": 0, "rejected": 0,
        "errors": 0, "symbols_done": [], "finished_at": None, "error": None,
    })
    await _scan_state_set(state)

    BATCH = 3
    try:
        for i in range(0, len(symbols_with_meta), BATCH):
            batch = symbols_with_meta[i: i + BATCH]
            results = await _aio.gather(
                *[
                    run_investment_workflow(
                        symbol=s["symbol"],
                        exchange=s["exchange"],
                        direction_bias=s.get("direction_bias"),
                    )
                    for s in batch
                ],
                return_exceptions=True,
            )
            now = datetime.now(timezone.utc)
            analyzed_symbols: list[str] = []
            for s, r in zip(batch, results):
                state["scanned"] += 1
                state["symbols_done"].append(s["symbol"])
                if isinstance(r, Exception):
                    state["errors"] += 1
                elif isinstance(r, dict) and r.get("workflow_status") in ("completed", "saved"):
                    state["approved"] += 1
                    analyzed_symbols.append(s["symbol"])
                else:
                    state["rejected"] += 1

            # Update last_analyzed_at so next pre-screener run rotates correctly
            if analyzed_symbols:
                try:
                    async with AsyncSessionLocal() as db:
                        await db.execute(
                            sa_update(AssetModel)
                            .where(AssetModel.symbol.in_(analyzed_symbols))
                            .values(last_analyzed_at=now)
                        )
                        await db.commit()
                except Exception as db_exc:
                    logger.warning("Failed to update last_analyzed_at", error=str(db_exc))

            await _scan_state_set(state)
            await _aio.sleep(1)
    except Exception as exc:
        state["error"] = str(exc)
    finally:
        state["running"] = False
        state["finished_at"] = datetime.now(timezone.utc).isoformat()
        await _scan_state_set(state)


@router.post("/pool/scan-now")
async def scan_pool_now(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Start a full AI scan of all active pool stocks in the background.
    Returns immediately — poll GET /pool/scan-status for progress.
    """
    import asyncio
    from sqlalchemy import select
    from app.db.models.asset import Asset

    current = await _scan_state_get()
    if current.get("running"):
        return {"started": False, "message": "Scan already running", "status": current}

    result = await db.execute(select(Asset).where(Asset.is_active_in_pool == True))
    assets = result.scalars().all()

    if not assets:
        return {"started": False, "error": "No assets in active pool. Run the screener first."}

    symbols_meta = [
        {"symbol": a.symbol, "exchange": a.exchange.value, "direction_bias": getattr(a, "direction_bias", None)}
        for a in assets
    ]

    # Write initial state to Redis before starting the task
    init_state = dict(_SCAN_DEFAULT)
    init_state.update({
        "running": True, "total": len(symbols_meta),
        "started_at": datetime.now(timezone.utc).isoformat(),
    })
    await _scan_state_set(init_state)

    asyncio.create_task(_run_scan_background(symbols_meta))

    return {
        "started": True,
        "total": len(symbols_meta),
        "message": f"Scanning {len(symbols_meta)} stocks in background. Poll /pool/scan-status for progress.",
    }


@router.get("/pool/scan-status")
async def scan_status(current_user: User = Depends(get_current_active_user)):
    """Return current background scan progress (reads from Redis — shared across all workers)."""
    return await _scan_state_get()


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
    active_pool = await db.execute(
        select(sqlfunc.count(Asset.id)).where(Asset.is_active_in_pool == True)
    )
    seeded = await db.execute(
        select(sqlfunc.count(Asset.id)).where(
            Asset.is_active_in_pool == True, Asset.in_universe == False
        )
    )

    top_result = await db.execute(
        select(Asset.symbol, Asset.long_score)
        .where(Asset.is_active_in_pool == True)
        .order_by(Asset.long_score.desc(), Asset.symbol.asc())
        .limit(20)
    )

    return {
        "universe_total": total_universe.scalar(),
        "seeded_pool": seeded.scalar(),
        "active_pool": active_pool.scalar(),
        "top_candidates": [
            {"symbol": r[0], "score": round(r[1], 1)}
            for r in top_result.fetchall()
        ],
    }


# ─── Master List ──────────────────────────────────────────────────────────────

@router.get("/quarterly-scan/status")
async def get_quarterly_scan_status():
    """Return current quarterly scan progress (for Fund Dashboard polling)."""
    from app.workers.quarterly_scanner import get_quarterly_scan_status
    return await get_quarterly_scan_status()


@router.post("/quarterly-scan/trigger")
async def trigger_quarterly_scan_manual(
    current_user: User = Depends(get_current_active_user),
):
    """Admin: manually trigger a quarterly scan outside the normal earnings season."""
    from app.workers.quarterly_scanner import trigger_quarterly_scan
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    q_num = (now.month - 1) // 3 + 1
    quarter = f"Q{q_num}-{now.year}"
    started = await trigger_quarterly_scan(quarter=quarter)
    return {"started": started, "quarter": quarter}


@router.get("/master-list")
async def get_master_list(db: AsyncSession = Depends(get_db)):
    """Return the active quarterly master list of curated stock picks."""
    from app.db.models.master_list import MasterListEntry

    result = await db.execute(
        select(MasterListEntry)
        .where(MasterListEntry.is_active == True)
        .order_by(MasterListEntry.confidence_score.desc())
    )
    entries = result.scalars().all()
    quarter = entries[0].quarter if entries else None
    return {
        "quarter": quarter,
        "entries": [
            {
                "id": e.id,
                "symbol": e.symbol,
                "asset_name": e.asset_name,
                "recommendation_type": e.recommendation_type,
                "confidence_score": e.confidence_score,
                "target_price": e.target_price,
                "stop_loss": e.stop_loss,
                "current_price": e.current_price,
                "expected_return_pct": e.expected_return_pct,
                "thesis": e.thesis,
                "sector": e.sector,
                "quarter": e.quarter,
                "published_at": e.published_at.isoformat() if e.published_at else None,
                "recommendation_id": e.recommendation_id,
            }
            for e in entries
        ],
    }


@router.post("/master-list/publish")
async def publish_master_list(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Admin: publish a new quarterly master list from top approved recommendations.

    Deactivates all existing entries, then creates new entries from:
    - Top 30 BUY / STRONG_BUY approved recommendations
    - Top 20 SELL / STRONG_SELL approved recommendations
    """
    from app.db.models.master_list import MasterListEntry
    from app.db.models.recommendation import Recommendation, RecommendationStatus, RecommendationType
    from app.db.models.asset import Asset as AssetModel
    from sqlalchemy import update as sa_update

    now = datetime.now(timezone.utc)
    month = now.month
    quarter_num = (month - 1) // 3 + 1
    quarter = f"Q{quarter_num}-{now.year}"

    # Snapshot old active symbols BEFORE deactivating (for diff notification later)
    old_symbols_result = await db.execute(
        select(MasterListEntry.symbol).where(MasterListEntry.is_active == True)
    )
    old_symbols: set = {r[0] for r in old_symbols_result.all()}

    # Deactivate all existing master list entries
    await db.execute(sa_update(MasterListEntry).values(is_active=False))

    approved_statuses = [
        RecommendationStatus.APPROVED,
        RecommendationStatus.PRESENTED_TO_USER,
        RecommendationStatus.ACTIONED,
    ]
    buy_types = [RecommendationType.BUY, RecommendationType.STRONG_BUY]
    sell_types = [RecommendationType.SELL, RecommendationType.STRONG_SELL]

    # Top 30 buys
    buy_result = await db.execute(
        select(Recommendation, AssetModel.name.label("asset_name"), AssetModel.sector)
        .join(AssetModel, AssetModel.id == Recommendation.asset_id)
        .where(Recommendation.recommendation_type.in_(buy_types))
        .where(Recommendation.status.in_(approved_statuses))
        .order_by(Recommendation.confidence_score.desc())
        .limit(30)
    )
    buy_rows = buy_result.all()

    # Top 20 sells
    sell_result = await db.execute(
        select(Recommendation, AssetModel.name.label("asset_name"), AssetModel.sector)
        .join(AssetModel, AssetModel.id == Recommendation.asset_id)
        .where(Recommendation.recommendation_type.in_(sell_types))
        .where(Recommendation.status.in_(approved_statuses))
        .order_by(Recommendation.confidence_score.desc())
        .limit(20)
    )
    sell_rows = sell_result.all()

    entries = []
    for rec, asset_name, sector in (buy_rows + sell_rows):
        thesis = rec.fundamental_analysis.get("thesis") if rec.fundamental_analysis else None
        entry = MasterListEntry(
            symbol=rec.symbol,
            asset_name=asset_name,
            recommendation_type=rec.recommendation_type.value if hasattr(rec.recommendation_type, "value") else rec.recommendation_type,
            confidence_score=rec.confidence_score,
            target_price=rec.target_price,
            stop_loss=rec.stop_loss,
            current_price=rec.current_price_at_recommendation,
            expected_return_pct=rec.expected_return_pct,
            thesis=thesis,
            sector=sector,
            quarter=quarter,
            published_at=now,
            is_active=True,
            recommendation_id=rec.id,
        )
        entries.append(entry)

    db.add_all(entries)
    await db.flush()

    # Compute Master List diff — stocks that were in old list but NOT in new one
    new_symbols: set = {e.symbol for e in entries}
    dropped_symbols: set = old_symbols - new_symbols

    try:
        from app.db.models.user import User as UserModel
        from app.db.models.portfolio import Portfolio
        from app.db.models.notification import NotificationType
        from app.services.notifications.service import NotificationService

        users_result = await db.execute(
            select(UserModel).where(UserModel.is_active == True)
        )
        all_users = users_result.scalars().all()

        notification_service = NotificationService()

        # 1. General "new master list published" notification to everyone
        for u in all_users:
            title = (
                f"רשימת המאסטר {quarter} פורסמה"
                if u.preferred_language == "he"
                else f"Master List {quarter} Published"
            )
            await notification_service.send_notification(
                user_id=u.id,
                recommendation_id=None,
                internal_detail={
                    "quarter": quarter,
                    "total": len(entries),
                    "buys": len(buy_rows),
                    "sells": len(sell_rows),
                    "dropped": list(dropped_symbols),
                },
                db=db,
                notification_type=NotificationType.SYSTEM,
                title=title,
            )

        # 2. Personal alert to users who hold stocks that were REMOVED from the list
        if dropped_symbols:
            holdings_result = await db.execute(
                select(Portfolio.user_id, Portfolio.symbol)
                .where(
                    Portfolio.symbol.in_(dropped_symbols),
                    Portfolio.quantity > 0,
                )
            )
            # Build map: user_id → list of dropped symbols they still hold
            user_dropped: dict = {}
            for user_id, sym in holdings_result.all():
                user_dropped.setdefault(user_id, []).append(sym)

            for user_id, held in user_dropped.items():
                symbols_str = ", ".join(held)
                await notification_service.send_notification(
                    user_id=user_id,
                    recommendation_id=None,
                    internal_detail={
                        "quarter": quarter,
                        "dropped_symbols": held,
                        "action_required": True,
                    },
                    db=db,
                    notification_type=NotificationType.SYSTEM,
                    title=(
                        f"⚠️ {symbols_str} — הוסרו מהמאסטר ליסט {quarter}. "
                        f"בדוק את הפוזיציה שלך ושקול האם למכור."
                    ),
                )

            logger.info(
                f"Master list publish: {len(dropped_symbols)} dropped symbols, "
                f"alerted {len(user_dropped)} users with active holdings"
            )

    except Exception as _notify_exc:
        logger.warning(f"Master list publish notifications failed: {_notify_exc}")

    return {
        "published": len(entries),
        "quarter": quarter,
        "buys": len(buy_rows),
        "sells": len(sell_rows),
        "dropped_from_previous": list(dropped_symbols),
    }
