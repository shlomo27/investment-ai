"""
Market Data API routes
GET /market/search, GET /market/asset/{symbol}, GET /market/tase/search, GET /market/pool
"""
import asyncio
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

    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

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
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    from app.db.seed import seed_asset_pool
    result = await seed_asset_pool(db)
    return result


@router.post("/universe/load")
async def load_universe_endpoint(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Load S&P 500 + S&P 400 constituents into the universe (admin action)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
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
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

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


# ─── Simulation / Testing ────────────────────────────────────────────────────

@router.post("/simulate/ta-scan-now")
async def simulate_ta_scan(
    current_user: User = Depends(get_current_active_user),
):
    """Admin: run TA scan immediately (normally runs every 30 min)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    import asyncio
    from app.workers.in_process_scheduler import job_daily_ta_scan
    asyncio.create_task(job_daily_ta_scan())
    return {"started": True, "message": "TA scan running in background — check notifications inbox in ~1 min"}


_AI_CHECK_KEY = "investment_ai:ai_engines_check"


async def _ai_check_state_get() -> dict:
    try:
        import redis.asyncio as aioredis
        from app.core.config import settings
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        raw = await r.get(_AI_CHECK_KEY)
        await r.aclose()
        return _json.loads(raw) if raw else {}
    except Exception:
        return {}


async def _ai_check_state_set(state: dict) -> None:
    try:
        import redis.asyncio as aioredis
        from app.core.config import settings
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await r.set(_AI_CHECK_KEY, _json.dumps(state), ex=3600)
        await r.aclose()
    except Exception:
        pass


async def _run_ai_engines_check(sym: str) -> None:
    """Background task: run one full analysis and store the per-engine report."""
    from app.agents.workflow import run_investment_workflow
    try:
        exchange = "TASE" if sym.endswith(".TA") else "NASDAQ"
        state = await run_investment_workflow(
            symbol=sym, exchange=exchange, trigger_type="MANUAL",
            trigger_details="ai-engines-check simulation",
        )
        result = await _build_ai_check_report(sym, state)
        result["running"] = False
        await _ai_check_state_set(result)
    except Exception as exc:
        logger.error(f"[ai-engines-check] failed: {exc}")
        await _ai_check_state_set({"running": False, "symbol": sym, "error": str(exc)})


async def _probe_grok(sym: str) -> dict:
    """Directly call the Grok X-sentiment source and surface its raw result,
    including any error (auth / model-not-found / no posts), so step-6 tells us
    exactly why grok/X is 0 instead of swallowing it."""
    from app.core.config import settings
    from app.services.market_data.sentiment_service import SentimentService
    if not (settings.XAI_API_KEY or "").strip():
        return {"ok": False, "detail": "XAI_API_KEY not set in this service"}
    if sym.endswith(".TA"):
        return {"ok": False, "detail": "skipped for TASE symbols"}
    try:
        res = await SentimentService()._get_grok_x_sentiment(sym)
    except Exception as e:
        return {"ok": False, "detail": f"call raised: {str(e)[:140]}"}
    if res.get("error"):
        return {"ok": False, "detail": f"model='{settings.XAI_MODEL}' → {res['error']}"}
    cnt = res.get("count", 0)
    return {
        "ok": cnt > 0,
        "detail": (f"model='{settings.XAI_MODEL}', posts={cnt}, score={res.get('score')}"
                   if cnt else f"model='{settings.XAI_MODEL}' returned 0 posts (no X activity or search off)"),
    }


def _claude_detail(claude_ok: bool, senior: dict) -> str:
    """Human-readable Claude line. Distinguishes a full senior decision (with a
    confidence %) from an early rejection (fundamental confidence too low — no
    committee deliberation, so no confidence number)."""
    if not claude_ok:
        return "fundamental/senior missing — check ANTHROPIC_API_KEY"
    rec = senior.get("final_recommendation", "?")
    conf = senior.get("decision_confidence")
    if conf is not None:
        return f"fundamental+senior OK — {rec} ({conf}%)"
    reason = senior.get("rejection_reasoning")
    if reason:
        return f"OK — {rec} (early-rejected: {str(reason)[:80]})"
    return f"fundamental+senior OK — {rec}"


async def _build_ai_check_report(sym: str, state: dict) -> dict:
    def _engine(analysis, label_field=None):
        analysis = analysis or {}
        reason = analysis.get("skipped_reason")
        if reason:
            return {"ok": False, "detail": reason}
        if not analysis:
            return {"ok": False, "detail": "no output"}
        return {"ok": True, "detail": str(analysis.get(label_field, "OK"))[:120] if label_field else "OK"}

    fundamental = state.get("fundamental_analysis") or {}
    senior = state.get("senior_decision") or {}
    # Detect the fundamental fallback (Claude call failed / JSON truncated):
    # it returns confidence 0.0 with a system-error thesis + "Analysis failed:"
    # in analyst_notes. That must read as a FAILURE, not a green "OK".
    fund_notes = str(fundamental.get("analyst_notes") or "")
    fund_thesis = str(fundamental.get("thesis") or "")
    claude_failed = fund_notes.startswith("Analysis failed") or "system error" in fund_thesis.lower()
    claude_ok = bool(fundamental.get("confidence_score") is not None and senior) and not claude_failed

    # News source breakdown — proves which of the configured feeds delivered
    raw = state.get("data_fetcher_output") or {}
    news_items = raw.get("news_items") or []
    news_sources: Dict[str, int] = {}
    for item in news_items:
        src = (item.get("source") or "unknown") if isinstance(item, dict) else "unknown"
        news_sources[src] = news_sources.get(src, 0) + 1

    # Full data-source coverage report — every feed the DataFetcher pulls
    sentiment = raw.get("social_sentiment") or {}
    # Probe Finnhub directly so we can tell "stock has no P/E" from
    # "Finnhub key missing/not returning it".
    from app.services.market_data.finnhub_service import get_finnhub_service
    fin = get_finnhub_service()
    finnhub_pe = None
    finnhub_configured = fin.is_configured()
    if finnhub_configured and not sym.endswith(".TA"):
        try:
            fin_metrics = await fin.get_basic_financials(sym)
            finnhub_pe = (fin_metrics or {}).get("pe_ratio")
        except Exception:
            pass

    pe = raw.get("pe_ratio")
    fwd_pe = raw.get("forward_pe")
    data_sources = {
        "price_fundamentals": {
            "ok": bool(raw.get("price")),
            "detail": (
                f"price={raw.get('price')}, market_cap={'✓' if raw.get('market_cap') else '✗'}, "
                f"P/E={pe if pe is not None else '—'}, fwdP/E={fwd_pe if fwd_pe is not None else '—'} "
                f"| Finnhub: {'configured' if finnhub_configured else 'NOT configured'}, "
                f"P/E={finnhub_pe if finnhub_pe is not None else '—'}"
            ),
        },
        "social_sentiment": {
            "ok": bool(sentiment.get("mentions")),
            "detail": (
                f"score={sentiment.get('score', 0)}, mentions={sentiment.get('mentions', 0)} "
                f"(twitter={sentiment.get('tweet_count', 0)}, reddit={sentiment.get('reddit_post_count', 0)}, "
                f"stocktwits={sentiment.get('stocktwits_post_count', 0)}, grok/X={sentiment.get('grok_x_post_count', 0)})"
            ),
        },
        "grok_x": await _probe_grok(sym),
        "news": {
            "ok": len(news_items) > 0,
            "detail": f"{len(news_items)} articles / {len(news_sources)} feeds",
        },
        "insider_activity": {
            "ok": raw.get("insider_activity") is not None,
            "detail": "OK" if raw.get("insider_activity") is not None else "no data",
        },
        "sec_filings": {
            "ok": raw.get("sec_filings") is not None,
            "detail": "OK" if raw.get("sec_filings") is not None else "no data",
        },
    }

    return {
        "symbol": sym,
        "workflow_status": state.get("workflow_status"),
        "recommendation_id": state.get("recommendation_id"),
        "error": state.get("error"),
        "news_articles_total": len(news_items),
        "news_sources": news_sources,
        "data_sources": data_sources,
        "fetch_errors": raw.get("fetch_errors") or [],
        "engines": {
            "claude": {
                "ok": claude_ok,
                "detail": (f"fundamental agent FAILED → {fund_notes[:110]}"
                           if claude_failed else _claude_detail(claude_ok, senior)),
            },
            "openai_news": _engine(state.get("news_analysis"), "overall_sentiment"),
            "gemini_macro": _engine(state.get("macro_analysis"), "sector_outlook"),
        },
    }


@router.post("/simulate/ai-engines-check")
async def simulate_ai_engines_check(
    symbol: str = "AAPL",
    current_user: User = Depends(get_current_active_user),
):
    """
    Admin: START a full real analysis in the background and report which AI
    engine actually ran. Returns immediately; poll /simulate/ai-engines-status
    for the result. Runs in background so mobile/long connections don't drop
    (the analysis takes 1-3 min). Costs ~$0.10-0.25 per run.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    sym = symbol.upper().strip()
    current = await _ai_check_state_get()
    if current.get("running"):
        return {"started": False, "already_running": True, "symbol": current.get("symbol")}

    await _ai_check_state_set({"running": True, "symbol": sym})
    asyncio.create_task(_run_ai_engines_check(sym))
    return {"started": True, "symbol": sym,
            "message": "Analysis running in background (1-3 min) — poll ai-engines-status"}


@router.get("/simulate/ai-engines-status")
async def simulate_ai_engines_status(current_user: User = Depends(get_current_active_user)):
    """Poll the latest AI-engines-check result (shared via Redis across workers)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return await _ai_check_state_get()


@router.get("/telegram/discover-chats")
async def telegram_discover_chats():
    """
    List every chat/channel our bot can currently see (via getUpdates), so you
    can copy the admin channel's chat_id without fiddling with URLs. Public on
    purpose (browser-accessible) — returns only non-sensitive chat ids/titles,
    never the bot token. Post a message in the target channel first, then call.
    """
    import httpx as _httpx
    from app.core.config import settings
    token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
    if not token or token.startswith("your_"):
        return {"error": "TELEGRAM_BOT_TOKEN not configured"}
    chats = {}
    try:
        async with _httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"https://api.telegram.org/bot{token}/getUpdates")
            data = resp.json()
        for upd in data.get("result", []):
            msg = upd.get("channel_post") or upd.get("message") or upd.get("my_chat_member") or {}
            chat = msg.get("chat") or {}
            cid = chat.get("id")
            if cid is not None:
                chats[str(cid)] = {
                    "chat_id": cid,
                    "title": chat.get("title") or chat.get("username") or chat.get("first_name") or "?",
                    "type": chat.get("type"),
                }
    except Exception as e:
        return {"error": str(e)[:200]}
    return {
        "found": list(chats.values()),
        "hint": "Copy the chat_id whose title is your admin channel into TELEGRAM_ADMIN_CHAT_ID in Railway.",
        "note": "If empty: post a fresh message in the channel and call again (Telegram only keeps recent updates).",
    }


@router.post("/simulate/test-admin-alert")
async def simulate_test_admin_alert(current_user: User = Depends(get_current_active_user)):
    """Admin: send a test message to the ADMIN telegram channel + report today's est. spend."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    from app.services.notifications.telegram_service import get_telegram_service
    from app.workers.cost_guard import get_today_spend
    from app.core.config import settings
    sent = await get_telegram_service().send_admin_alert(
        "🛠️ <b>בדיקת ערוץ אדמין</b>\nהתראות תפעוליות (כשל מנוע / תקרת הוצאה) יגיעו לכאן."
    )
    return {
        "admin_alert_sent": sent,
        "admin_chat_configured": bool(settings.TELEGRAM_ADMIN_CHAT_ID),
        "daily_budget_usd": settings.DAILY_CLAUDE_BUDGET_USD,
        "today_est_spend_usd": round(await get_today_spend(), 2),
    }


@router.post("/simulate/test-notification")
async def simulate_test_notification(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin: send a test notification to yourself via all configured channels."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    from app.services.notifications.service import NotificationService
    from app.db.models.notification import NotificationType
    from app.core.config import settings

    # Diagnostic check
    sg_key = settings.SENDGRID_API_KEY or ""
    twilio_sid = settings.TWILIO_ACCOUNT_SID or ""
    twilio_token = settings.TWILIO_AUTH_TOKEN or ""
    firebase_ok = bool(settings.FIREBASE_CREDENTIALS_JSON or settings.FIREBASE_CREDENTIALS_PATH)

    tg_token = settings.TELEGRAM_BOT_TOKEN or ""
    tg_chat = settings.TELEGRAM_CHAT_ID or ""
    tg_ok = bool(tg_token) and not tg_token.startswith("your_") and bool(tg_chat)

    diagnostics = {
        "push": {
            "enabled": current_user.notification_push,
            "has_token": bool(current_user.push_token),
            "firebase_configured": firebase_ok,
            "will_send": current_user.notification_push and bool(current_user.push_token) and firebase_ok,
        },
        "sms": {
            "enabled": current_user.notification_sms,
            "has_phone": bool(current_user.phone),
            "twilio_configured": bool(twilio_sid) and not twilio_sid.startswith("your_")
                                  and bool(twilio_token) and not twilio_token.startswith("your_"),
            "will_send": (current_user.notification_sms and bool(current_user.phone)
                          and bool(twilio_sid) and not twilio_sid.startswith("your_")
                          and bool(twilio_token) and not twilio_token.startswith("your_")),
        },
        "email": {
            "enabled": current_user.notification_email,
            "has_email": bool(current_user.email),
            "sendgrid_configured": bool(sg_key) and not sg_key.startswith("SG.xxx") and len(sg_key) >= 20,
            "will_send": (current_user.notification_email and bool(current_user.email)
                          and bool(sg_key) and not sg_key.startswith("SG.xxx") and len(sg_key) >= 20),
        },
        "telegram": {
            "configured": tg_ok,
            "has_bot_token": bool(tg_token) and not tg_token.startswith("your_"),
            "has_chat_id": bool(tg_chat),
            "will_send": tg_ok,
        },
    }

    svc = NotificationService()
    # For test notification, also send Telegram directly
    if tg_ok:
        from app.services.notifications.telegram_service import get_telegram_service
        tg_sent = await get_telegram_service().send_test_message()
        if tg_sent:
            diagnostics["telegram"]["test_sent"] = True

    notif = await svc.send_notification(
        user_id=current_user.id,
        recommendation_id=None,
        internal_detail={
            "type": "TEST",
            "message": "This is a test notification to verify push/SMS/email/telegram channels.",
        },
        db=db,
        notification_type=NotificationType.SYSTEM,
        title="🧪 Test Notification | בדיקת מערכת התראות",
    )
    return {
        "sent": notif is not None,
        "channels": notif.channels_sent if notif else [],
        "notification_id": notif.id if notif else None,
        "diagnostics": diagnostics,
    }


@router.post("/simulate/create-test-position")
async def simulate_create_test_position(
    symbol: str,
    quantity: float = 10.0,
    price: float = 100.0,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin: create a test portfolio position so TA alerts will fire for this symbol."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    from app.db.models.portfolio import Portfolio
    from sqlalchemy import select as sa_select

    symbol = symbol.upper()

    # Check if position already exists
    existing = await db.execute(
        sa_select(Portfolio).where(
            Portfolio.user_id == current_user.id,
            Portfolio.symbol == symbol,
        )
    )
    pos = existing.scalar_one_or_none()
    if pos:
        pos.quantity = quantity
        pos.avg_buy_price = price
    else:
        pos = Portfolio(
            user_id=current_user.id,
            symbol=symbol,
            quantity=quantity,
            avg_buy_price=price,
        )
        db.add(pos)

    await db.flush()
    return {
        "created": True,
        "symbol": symbol,
        "quantity": quantity,
        "avg_buy_price": price,
        "note": f"TA alerts for {symbol} will now fire to user {current_user.email}",
    }


@router.delete("/simulate/remove-test-position")
async def simulate_remove_test_position(
    symbol: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin: remove a test position after simulation."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    from app.db.models.portfolio import Portfolio
    from sqlalchemy import select as sa_select, delete as sa_delete

    symbol = symbol.upper()
    await db.execute(
        sa_delete(Portfolio).where(
            Portfolio.user_id == current_user.id,
            Portfolio.symbol == symbol,
        )
    )
    return {"removed": True, "symbol": symbol}


# ─── Earnings Status ─────────────────────────────────────────────────────────

@router.post("/earnings/check-now")
async def earnings_check_now(
    current_user: User = Depends(get_current_active_user),
):
    """Manually trigger an earnings queue check (admin action)."""
    from app.workers.earnings_watcher import job_earnings_queue_check
    result = await job_earnings_queue_check()
    return result


@router.post("/earnings/reset")
async def earnings_reset(
    current_user: User = Depends(get_current_active_user),
):
    """Clear all earnings Redis keys and start fresh (admin action)."""
    import redis.asyncio as aioredis
    from app.core.config import settings

    r = aioredis.from_url(settings.REDIS_URL)
    try:
        keys = [
            "investment_ai:earnings_queue",
            "investment_ai:earnings_details",
            "investment_ai:earnings_pending",
            "investment_ai:earnings_last_check",
            "investment_ai:earnings_scan_triggered",
        ]
        deleted = 0
        for k in keys:
            deleted += await r.delete(k)
        return {"reset": True, "keys_deleted": deleted}
    finally:
        await r.aclose()


@router.get("/earnings/status")
async def earnings_status(
    current_user: User = Depends(get_current_active_user),
):
    """Return current earnings queue status (for admin dashboard)."""
    import json as _json
    import redis.asyncio as aioredis
    from app.core.config import settings

    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        queue_count    = await r.scard("investment_ai:earnings_queue")
        details_raw    = await r.hgetall("investment_ai:earnings_details")
        pending_raw    = await r.hgetall("investment_ai:earnings_pending")
        last_check     = await r.get("investment_ai:earnings_last_check")
        scan_triggered = await r.get("investment_ai:earnings_scan_triggered")

        confirmed = []
        for sym, val in details_raw.items():
            try:
                d = _json.loads(val)
                confirmed.append({
                    "symbol": sym,
                    "earnings_date": d.get("earnings_date"),
                    "added_at": d.get("added_at"),
                    "status": "confirmed",
                })
            except Exception:
                pass
        confirmed.sort(key=lambda x: x.get("earnings_date", ""), reverse=True)

        pending = []
        for sym, val in pending_raw.items():
            try:
                d = _json.loads(val)
                pending.append({
                    "symbol": sym,
                    "earnings_date": d.get("report_date"),
                    "added_at": d.get("added_at"),
                    "status": "pending",
                })
            except Exception:
                pass
        pending.sort(key=lambda x: x.get("earnings_date", ""))

        return {
            "queue_count":     int(queue_count),
            "trigger_at":      settings.MIN_EARNINGS_TRIGGER,
            "companies":       confirmed,
            "pending":         pending,
            "last_check":      last_check,
            "scan_triggered":  scan_triggered,
            "fmp_configured":  bool(settings.FMP_API_KEY or settings.ALPHA_VANTAGE_KEY),
        }
    finally:
        await r.aclose()


# ─── Paper Trading ────────────────────────────────────────────────────────────

@router.get("/paper-trading/status")
async def paper_trading_status(
    current_user: User = Depends(get_current_active_user),
):
    """Get Alpaca paper trading account status, positions, and recent orders."""
    from app.services.market_data.alpaca_service import get_alpaca_service
    from app.core.config import settings

    alpaca = get_alpaca_service()
    configured = bool(settings.ALPACA_API_KEY and not settings.ALPACA_API_KEY.startswith("your_"))

    if not configured:
        return {
            "configured": False,
            "paper": True,
            "message": "Set ALPACA_API_KEY and ALPACA_API_SECRET in Railway to enable paper trading",
        }

    account, positions, orders = await asyncio.gather(
        alpaca.get_account(),
        alpaca.get_positions(),
        alpaca.get_closed_orders(limit=20),
        return_exceptions=True,
    )

    return {
        "configured": True,
        "paper": settings.ALPACA_PAPER,
        "account": account if not isinstance(account, Exception) else None,
        "positions": positions if not isinstance(positions, Exception) else [],
        "recent_orders": orders if not isinstance(orders, Exception) else [],
        "virtual_portfolio_value": settings.ALPACA_PAPER_PORTFOLIO_VALUE,
    }


# ─── Master List ──────────────────────────────────────────────────────────────

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


@router.post("/quarterly/run-batch")
async def run_quarterly_batch_now(
    current_user: User = Depends(get_current_active_user),
):
    """Admin: resume/run today's quarterly scan batch in the background.
    Deploys kill an in-flight batch and APScheduler won't refire until the
    next day — this lets the admin continue the queue immediately."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    import asyncio as _asyncio
    from app.core.config import settings
    from app.workers.quarterly_scanner import job_quarterly_scan_batch, REDIS_PREFIX
    import redis.asyncio as aioredis

    r = aioredis.from_url(settings.REDIS_URL)
    try:
        active = await r.get(REDIS_PREFIX + "active")
        if not active:
            return {"started": False, "reason": "no active quarterly scan"}
        running = await r.get(REDIS_PREFIX + "batch_running")
        if running:
            # Self-heal: the live batch heartbeats this flag with a 10-minute
            # TTL. A TTL beyond that is a stale lock (legacy 4h flag, or a
            # batch killed by a deploy) — clear it and start.
            ttl = await r.ttl(REDIS_PREFIX + "batch_running")
            if ttl is None or ttl > 610:
                await r.delete(REDIS_PREFIX + "batch_running")
                running = None
        if running:
            remaining = await r.llen(REDIS_PREFIX + "todo")
            return {"started": False, "reason": "batch already running", "remaining": remaining}
        await r.set(REDIS_PREFIX + "batch_running", "1", ex=600)
        remaining = await r.llen(REDIS_PREFIX + "todo")
    finally:
        await r.aclose()

    async def _run_and_clear():
        try:
            await job_quarterly_scan_batch()
        finally:
            r2 = aioredis.from_url(settings.REDIS_URL)
            try:
                await r2.delete(REDIS_PREFIX + "batch_running")
            finally:
                await r2.aclose()

    _asyncio.create_task(_run_and_clear())
    return {"started": True, "remaining_before": remaining}


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
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    from app.db.models.master_list import MasterListEntry
    from app.db.models.recommendation import Recommendation, RecommendationStatus, RecommendationType
    from app.db.models.asset import Asset as AssetModel
    from sqlalchemy import update as sa_update

    now = datetime.now(timezone.utc)
    month = now.month
    quarter_num = (month - 1) // 3 + 1
    quarter = f"Q{quarter_num}-{now.year}"

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
    seen_symbols: set = set()
    for rec, asset_name, sector in (buy_rows + sell_rows):
        # One entry per symbol — rows are confidence-sorted, so the first
        # occurrence is the best; older duplicate recommendations can't
        # multiply into the published list.
        if rec.symbol in seen_symbols:
            continue
        seen_symbols.add(rec.symbol)
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

    # Notify all active users that a new master list is published
    try:
        from app.db.models.user import User as UserModel
        from app.db.models.notification import NotificationType
        from app.services.notifications.service import NotificationService

        users_result = await db.execute(
            select(UserModel).where(UserModel.is_active == True)
        )
        all_users = users_result.scalars().all()

        notification_service = NotificationService()
        for u in all_users:
            title = (
                f"רשימת המאסטר {quarter} פורסמה"
                if u.preferred_language == "he"
                else f"Master List {quarter} Published"
            )
            await notification_service.send_notification(
                user_id=u.id,
                recommendation_id=None,
                internal_detail={"quarter": quarter, "total": len(entries), "buys": len(buy_rows), "sells": len(sell_rows)},
                db=db,
                notification_type=NotificationType.SYSTEM,
                title=title,
            )
    except Exception as _notify_exc:
        logger.warning(f"Master list publish notifications failed: {_notify_exc}")

    return {
        "published": len(entries),
        "quarter": quarter,
        "buys": len(buy_rows),
        "sells": len(sell_rows),
    }


# ─── Earnings Calendar ────────────────────────────────────────────────────────

@router.get("/earnings-calendar")
async def get_earnings_calendar(
    symbols: Optional[str] = Query(None, description="Comma-separated symbols, or omit for all watchlist"),
    days_ahead: int = Query(14, ge=1, le=90),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Return upcoming earnings dates for given symbols (or user's watchlist)."""
    from app.services.market_data.earnings_calendar_service import get_earnings_calendar_service
    from app.db.models.watchlist import Watchlist

    if symbols:
        symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    else:
        # Default set: stocks the user actually HOLDS plus their watchlist —
        # holdings are what upcoming earnings matter for most, and a fresh
        # user has an empty watchlist.
        from app.db.models.portfolio import Portfolio

        wl_result = await db.execute(
            select(Watchlist).where(Watchlist.user_id == current_user.id)
        )
        held_result = await db.execute(
            select(Portfolio.symbol).where(
                Portfolio.user_id == current_user.id, Portfolio.quantity > 0
            ).distinct()
        )
        symbol_list = sorted(
            {w.symbol for w in wl_result.scalars().all()}
            | {row[0] for row in held_result.all()}
        )

    if not symbol_list:
        return []

    return await get_earnings_calendar_service().get_upcoming_earnings(symbol_list, days_ahead)


# ─── Sector Performance Dashboard ────────────────────────────────────────────

@router.get("/sectors")
async def get_sector_performance(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Return weekly sector performance based on recommendation database."""
    from app.db.models.recommendation import Recommendation, RecommendationStatus
    from sqlalchemy import func as sqlfunc
    from app.db.models.asset import Asset as AssetModel

    result = await db.execute(
        select(
            AssetModel.sector,
            sqlfunc.count(Recommendation.id).label("rec_count"),
            sqlfunc.avg(Recommendation.confidence_score).label("avg_confidence"),
            sqlfunc.avg(Recommendation.expected_return_pct).label("avg_expected_return"),
        )
        .join(AssetModel, AssetModel.id == Recommendation.asset_id)
        .where(
            Recommendation.status == RecommendationStatus.APPROVED,
            AssetModel.sector.isnot(None),
        )
        .group_by(AssetModel.sector)
        .order_by(sqlfunc.avg(Recommendation.confidence_score).desc())
    )
    rows = result.all()

    sectors = []
    for row in rows:
        if row.sector:
            sectors.append({
                "sector": row.sector,
                "recommendation_count": row.rec_count,
                "avg_confidence": round(float(row.avg_confidence or 0), 1),
                "avg_expected_return_pct": round(float(row.avg_expected_return or 0), 1),
                "signal": "BULLISH" if (row.avg_expected_return or 0) > 0 else "BEARISH",
            })

    return {
        "sectors": sectors,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── Stock Comparison ────────────────────────────────────────────────────────

class CompareRequest(BaseModel):
    symbols: List[str]
    exchange: str = "NASDAQ"


@router.post("/compare")
async def compare_stocks(
    request: CompareRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Fetch and compare market data for 2 stocks side by side.
    """
    if len(request.symbols) < 2 or len(request.symbols) > 4:
        raise HTTPException(status_code=400, detail="Provide 2-4 symbols to compare")

    yahoo = YahooFinanceService()

    async def _fetch(symbol: str) -> Dict[str, Any]:
        try:
            data = await yahoo.get_stock_info(symbol.upper())
            return data or {"symbol": symbol, "error": "No data"}
        except Exception as e:
            return {"symbol": symbol, "error": str(e)}

    results = await asyncio.gather(*[_fetch(s) for s in request.symbols])

    comparison = {}
    metrics = ["price", "market_cap", "pe_ratio", "forward_pe", "peg_ratio",
               "revenue_growth", "profit_margin", "roe", "debt_to_equity",
               "free_cash_flow", "dividend_yield", "beta", "fifty_two_week_high",
               "fifty_two_week_low", "analyst_recommendation", "sector"]

    for symbol, data in zip(request.symbols, results):
        comparison[symbol.upper()] = {m: data.get(m) for m in metrics}
        comparison[symbol.upper()]["name"] = data.get("name", symbol)
        comparison[symbol.upper()]["error"] = data.get("error")

    return {
        "symbols": [s.upper() for s in request.symbols],
        "comparison": comparison,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── Insider Trading ─────────────────────────────────────────────────────────

@router.get("/insider/{symbol}")
async def get_insider_activity(
    symbol: str,
    days_back: int = Query(90, ge=7, le=365),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Fetch recent SEC Form 4 insider transactions for a symbol."""
    from app.services.market_data.insider_service import get_insider_service
    return await get_insider_service().get_insider_summary(symbol.upper())


# ─── SEC Filings ─────────────────────────────────────────────────────────────

@router.get("/sec-filings/{symbol}")
async def get_sec_filings(
    symbol: str,
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Fetch recent 10-K and 10-Q filing metadata from SEC EDGAR."""
    from app.services.market_data.sec_service import get_sec_service
    return await get_sec_service().get_filings_summary(symbol.upper())
