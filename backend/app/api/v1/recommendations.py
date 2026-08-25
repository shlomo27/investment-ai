"""
Recommendations API routes - the "Inbox" that users see after login
GET /recommendations, GET /recommendations/{id}, POST /recommendations/{id}/acknowledge
GET /inbox (notification inbox with full AI details)
"""
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_

from app.core.database import get_db
from app.core.security import get_current_active_user
from app.db.models.user import User
from app.db.models.recommendation import Recommendation, RecommendationStatus, RecommendationType
from app.db.models.notification import Notification, NotificationType
from app.db.models.asset import Asset, RiskLevel

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


class RecommendationResponse(BaseModel):
    id: int
    symbol: str
    recommendation_type: RecommendationType
    status: RecommendationStatus
    confidence_score: float
    target_price: Optional[float]
    stop_loss: Optional[float]
    current_price_at_recommendation: Optional[float]
    fundamental_analysis: Optional[Dict[str, Any]]
    fundamental_notes: Optional[str]
    sentiment_data: Optional[Dict[str, Any]]
    senior_review_notes: Optional[str]
    senior_notes: Optional[str]
    technical_analysis: Optional[Dict[str, Any]]
    risk_factors: Optional[List]
    expected_return_pct: Optional[float]
    trigger_type: Optional[str] = None
    trigger_details: Optional[str] = None
    asset_name: Optional[str]
    sector: Optional[str]
    risk_level: Optional[str] = None
    beta: Optional[float] = None
    created_at: datetime
    approved_at: Optional[datetime]
    presented_at: Optional[datetime]

    class Config:
        from_attributes = True


class NotificationInboxResponse(BaseModel):
    id: int
    recommendation_id: Optional[int]
    notification_type: NotificationType
    title: Optional[str]
    external_message: str
    internal_detail: Optional[Dict[str, Any]]
    is_read: bool
    sent_at: datetime
    read_at: Optional[datetime]
    # State of the recommendation this message was about, resolved now rather
    # than when it was sent. A message outlives the recommendation it announced,
    # so without this a BUY alert stays on screen pointing at a stock that has
    # since left the feed — and the reader searches for it and finds nothing.
    recommendation_live: Optional[bool] = None
    recommendation_current_type: Optional[str] = None

    class Config:
        from_attributes = True


def _beta_of(rec: Recommendation, asset: Optional[Asset]) -> Optional[float]:
    """Beta for display: this analysis's own reading, falling back to the
    asset's stored one. Returns None rather than a guess when neither exists —
    a missing volatility figure must not read as a low one."""
    raw = rec.data_fetcher_raw or {}
    value = raw.get("beta")
    if value is None and asset is not None:
        value = asset.beta
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if 0 < value < 10 else None


@router.get("/", response_model=List[RecommendationResponse])
async def get_recommendations(
    status_filter: Optional[str] = None,
    # 20 was low enough that a live recommendation could sit outside the feed
    # entirely: an alert would arrive, the client would go looking for the
    # stock, and it was not there.
    limit: int = 200,
    offset: int = 0,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get approved recommendations.
    After login, users see full AI analysis details.
    """
    query = select(Recommendation).where(
        Recommendation.status.in_([
            RecommendationStatus.APPROVED,
            RecommendationStatus.PRESENTED_TO_USER,
            # ACTIONED = the user recorded a trade on it — they HOLD the stock,
            # so its analysis must stay reachable in the feed.
            RecommendationStatus.ACTIONED,
        ])
    )

    if status_filter:
        try:
            status_enum = RecommendationStatus(status_filter.upper())
            query = select(Recommendation).where(Recommendation.status == status_enum)
        except ValueError:
            pass

    # User-selected content preferences (self-service display filters the user
    # controls in Settings — NOT personalized advice): hide short-side signals
    # and/or high-volatility stocks unless the user opted in to see them.
    #
    # These MUST be applied before the limit. Filtering the page after slicing
    # it meant a hidden row was never replaced by the next eligible one: ask
    # for 20, hide 5, get 15 — and the five that should have taken their place
    # were simply never fetched.
    _short_types = (RecommendationType.SELL, RecommendationType.STRONG_SELL)
    _volatile_levels = (RiskLevel.HIGH, RiskLevel.VERY_HIGH)

    if not current_user.allows_short:
        query = query.where(Recommendation.recommendation_type.notin_(_short_types))

    if not current_user.allows_volatile:
        volatile_symbols = (
            select(Asset.symbol).where(Asset.risk_level.in_(_volatile_levels))
        ).scalar_subquery()
        query = query.where(Recommendation.symbol.notin_(volatile_symbols))

    query = query.order_by(desc(Recommendation.created_at)).offset(offset).limit(limit)
    result = await db.execute(query)
    recommendations = result.scalars().all()

    # Enrich with asset data
    symbols = [r.symbol for r in recommendations]
    assets_result = await db.execute(select(Asset).where(Asset.symbol.in_(symbols)))
    assets = {a.symbol: a for a in assets_result.scalars().all()}

    response = []
    for rec in recommendations:
        asset = assets.get(rec.symbol)
        response.append(RecommendationResponse(
            id=rec.id,
            symbol=rec.symbol,
            recommendation_type=rec.recommendation_type,
            status=rec.status,
            confidence_score=rec.confidence_score,
            target_price=rec.target_price,
            stop_loss=rec.stop_loss,
            current_price_at_recommendation=rec.current_price_at_recommendation,
            fundamental_analysis=rec.fundamental_analysis,
            fundamental_notes=rec.fundamental_notes,
            sentiment_data=rec.sentiment_data,
            senior_review_notes=rec.senior_review_notes,
            senior_notes=rec.senior_notes,
            technical_analysis=rec.technical_analysis,
            risk_factors=rec.risk_factors,
            expected_return_pct=rec.expected_return_pct,
            trigger_type=rec.trigger_type,
            trigger_details=rec.trigger_details,
            asset_name=asset.name if asset else None,
            risk_level=asset.risk_level.value if asset and asset.risk_level else None,
            # Prefer the beta measured by this analysis over the asset-level
            # one: the card states the volatility that was true when the
            # committee formed its view, not whatever a later scan overwrote.
            beta=_beta_of(rec, asset),
            sector=asset.sector if asset else None,
            created_at=rec.created_at,
            approved_at=rec.approved_at,
            presented_at=rec.presented_at,
        ))

    return response


@router.get("/hidden-count")
async def hidden_by_preferences(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """How many live recommendations the user's own display settings hide.

    Without this the filters are invisible: a stock is approved, appears in
    the scan log, and is simply absent from the feed with no way to tell that
    a preference — not a fault — removed it.
    """
    from sqlalchemy import func as sqlfunc

    live = [
        RecommendationStatus.APPROVED,
        RecommendationStatus.PRESENTED_TO_USER,
        RecommendationStatus.ACTIONED,
    ]
    _short_types = (RecommendationType.SELL, RecommendationType.STRONG_SELL)
    _volatile_levels = (RiskLevel.HIGH, RiskLevel.VERY_HIGH)

    async def _count(condition):
        q = select(sqlfunc.count(Recommendation.id)).where(
            Recommendation.status.in_(live), condition
        )
        return (await db.execute(q)).scalar() or 0

    hidden_short = 0
    if not current_user.allows_short:
        hidden_short = await _count(Recommendation.recommendation_type.in_(_short_types))

    hidden_volatile = 0
    if not current_user.allows_volatile:
        volatile_symbols = (
            select(Asset.symbol).where(Asset.risk_level.in_(_volatile_levels))
        ).scalar_subquery()
        # Exclude ones already counted as short so the total is not double-counted.
        cond = Recommendation.symbol.in_(volatile_symbols)
        if not current_user.allows_short:
            cond = and_(cond, Recommendation.recommendation_type.notin_(_short_types))
        hidden_volatile = await _count(cond)

    return {
        "hidden_total": hidden_short + hidden_volatile,
        "hidden_short": hidden_short,
        "hidden_volatile": hidden_volatile,
    }


@router.get("/inbox", response_model=List[NotificationInboxResponse])
async def get_inbox(
    unread_only: bool = False,
    notification_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    The main notification inbox. Authenticated users see full internal details here.
    This is the only place where the full AI analysis is exposed.

    Paged newest-first. Ask for the next page with `offset`; a short page means
    there are no more — an inbox that only ever showed the newest 50 left older
    alerts unreachable after a few weeks away.
    """
    query = select(Notification).where(Notification.user_id == current_user.id)

    if unread_only:
        query = query.where(Notification.is_read == False)

    if notification_type:
        try:
            query = query.where(
                Notification.notification_type == NotificationType(notification_type.upper())
            )
        except ValueError:
            pass  # unknown type — ignore the filter rather than return nothing

    query = query.order_by(desc(Notification.sent_at)).offset(offset).limit(limit)
    result = await db.execute(query)
    notifications = result.scalars().all()

    # Mark recommendations as presented_to_user
    rec_ids = [n.recommendation_id for n in notifications if n.recommendation_id]
    if rec_ids:
        recs_result = await db.execute(
            select(Recommendation).where(
                Recommendation.id.in_(rec_ids),
                Recommendation.status == RecommendationStatus.APPROVED,
            )
        )
        recs = recs_result.scalars().all()
        for rec in recs:
            rec.status = RecommendationStatus.PRESENTED_TO_USER
            if not rec.presented_at:
                rec.presented_at = datetime.utcnow()

    # Resolve each linked recommendation's CURRENT state in one query.
    live_statuses = {
        RecommendationStatus.APPROVED,
        RecommendationStatus.PRESENTED_TO_USER,
        RecommendationStatus.ACTIONED,
    }
    rec_state: Dict[int, Any] = {}
    all_rec_ids = [n.recommendation_id for n in notifications if n.recommendation_id]
    if all_rec_ids:
        state_rows = await db.execute(
            select(Recommendation.id, Recommendation.status, Recommendation.recommendation_type)
            .where(Recommendation.id.in_(all_rec_ids))
        )
        rec_state = {r[0]: (r[1], r[2]) for r in state_rows.all()}

    out = []
    for n in notifications:
        item = NotificationInboxResponse.from_orm(n)
        state = rec_state.get(n.recommendation_id) if n.recommendation_id else None
        if state:
            status_val, type_val = state
            item.recommendation_live = status_val in live_statuses
            item.recommendation_current_type = (
                type_val.value if hasattr(type_val, "value") else str(type_val)
            )
        out.append(item)
    return out


@router.get("/unread-count")
async def get_unread_count(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get count of unread notifications."""
    from sqlalchemy import func
    result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
    )
    count = result.scalar_one_or_none() or 0
    return {"unread_count": count}


@router.get("/scan-activity")
async def get_scan_activity(
    days: int = 7,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Transparency log: EVERY analysis the pipeline produced in the last N
    days — approved, HOLD, rejected (with the committee's reasoning) and
    superseded — so users can see what was scanned and why nothing new
    appeared in the feed.
    """
    from datetime import datetime, timezone, timedelta

    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(Recommendation)
        .where(Recommendation.created_at >= since)
        .order_by(desc(Recommendation.created_at))
        .limit(300)
    )
    recs = result.scalars().all()

    items = []
    counts = {"approved_buy": 0, "approved_sell": 0, "hold": 0, "rejected": 0,
              "superseded": 0, "not_analyzed": 0}
    LIVE = {
        RecommendationStatus.APPROVED,
        RecommendationStatus.PRESENTED_TO_USER,
        RecommendationStatus.ACTIONED,
    }
    for r in recs:
        rec_type = r.recommendation_type.value if r.recommendation_type else "HOLD"
        # A run that aborted before the committee decided is not a rejection.
        # It was shown as one — same label, blank confidence, no reasoning —
        # which made a data outage look like a verdict on the stock.
        abort_reason = (r.data_fetcher_raw or {}).get("abort_reason")
        if abort_reason:
            bucket = "not_analyzed"
        elif r.status == RecommendationStatus.REJECTED:
            bucket = "rejected"
        elif r.status == RecommendationStatus.DISMISSED:
            bucket = "superseded"
        elif r.status in LIVE and rec_type in ("BUY", "STRONG_BUY"):
            bucket = "approved_buy"
        elif r.status in LIVE and rec_type in ("SELL", "STRONG_SELL"):
            bucket = "approved_sell"
        elif r.status in LIVE:
            bucket = "hold"
        else:
            bucket = "rejected"
        counts[bucket] = counts.get(bucket, 0) + 1
        items.append({
            "id": r.id,
            "symbol": r.symbol,
            "recommendation_type": rec_type,
            "status": r.status.value,
            "bucket": bucket,
            "abort_reason": abort_reason,
            "confidence_score": r.confidence_score,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "reason": (r.senior_review_notes or r.senior_notes or "")[:500],
            "trigger_type": r.trigger_type,
        })

    return {"days": days, "total": len(items), "counts": counts, "items": items}


@router.get("/{recommendation_id}", response_model=RecommendationResponse)
async def get_recommendation(
    recommendation_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific recommendation with full AI analysis detail."""
    result = await db.execute(
        select(Recommendation).where(Recommendation.id == recommendation_id)
    )
    rec = result.scalar_one_or_none()

    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")

    asset_result = await db.execute(select(Asset).where(Asset.symbol == rec.symbol))
    asset = asset_result.scalar_one_or_none()

    return RecommendationResponse(
        id=rec.id,
        symbol=rec.symbol,
        recommendation_type=rec.recommendation_type,
        status=rec.status,
        confidence_score=rec.confidence_score,
        target_price=rec.target_price,
        stop_loss=rec.stop_loss,
        current_price_at_recommendation=rec.current_price_at_recommendation,
        fundamental_analysis=rec.fundamental_analysis,
        fundamental_notes=rec.fundamental_notes,
        sentiment_data=rec.sentiment_data,
        senior_review_notes=rec.senior_review_notes,
        senior_notes=rec.senior_notes,
        technical_analysis=rec.technical_analysis,
        risk_factors=rec.risk_factors,
        expected_return_pct=rec.expected_return_pct,
        trigger_type=rec.trigger_type,
        trigger_details=rec.trigger_details,
        asset_name=asset.name if asset else None,
        risk_level=asset.risk_level.value if asset and asset.risk_level else None,
        sector=asset.sector if asset else None,
        created_at=rec.created_at,
        approved_at=rec.approved_at,
        presented_at=rec.presented_at,
    )


@router.post("/{recommendation_id}/acknowledge")
async def acknowledge_recommendation(
    recommendation_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a recommendation as acknowledged/dismissed by the user."""
    result = await db.execute(
        select(Recommendation).where(Recommendation.id == recommendation_id)
    )
    rec = result.scalar_one_or_none()

    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")

    if rec.status not in (RecommendationStatus.APPROVED, RecommendationStatus.PRESENTED_TO_USER):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot acknowledge recommendation with status {rec.status}",
        )

    rec.status = RecommendationStatus.DISMISSED

    # Mark related notifications as read
    notif_result = await db.execute(
        select(Notification).where(
            Notification.recommendation_id == recommendation_id,
            Notification.user_id == current_user.id,
        )
    )
    for notif in notif_result.scalars().all():
        notif.is_read = True
        notif.read_at = datetime.utcnow()

    return {"message": "Recommendation acknowledged", "id": recommendation_id}


@router.post("/inbox/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a notification as read."""
    from app.services.notifications.service import get_notification_service
    svc = get_notification_service()
    success = await svc.mark_as_read(notification_id, current_user.id, db)

    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    return {"message": "Marked as read", "id": notification_id}


@router.delete("/inbox/{notification_id}")
async def delete_notification(
    notification_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete one notification from the inbox."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    await db.delete(notification)
    await db.flush()
    return {"deleted": True, "id": notification_id}


@router.delete("/inbox")
async def clear_read_notifications(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Clear every notification already read.

    Scoped to read ones on purpose: a single button that wiped unread alerts
    could silently discard a sell signal the user had not opened yet.
    """
    from sqlalchemy import delete as sa_delete

    result = await db.execute(
        sa_delete(Notification).where(
            Notification.user_id == current_user.id,
            Notification.is_read == True,
        )
    )
    await db.flush()
    return {"deleted": result.rowcount or 0}


@router.post("/{recommendation_id}/request-technical")
async def request_technical_analysis(
    recommendation_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger on-demand technical analysis for a recommendation.
    Runs the TechnicalAnalystAgent and updates the recommendation.
    """
    result = await db.execute(
        select(Recommendation).where(Recommendation.id == recommendation_id)
    )
    rec = result.scalar_one_or_none()

    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")

    # Fetch asset for exchange info
    asset_result = await db.execute(select(Asset).where(Asset.symbol == rec.symbol))
    asset = asset_result.scalar_one_or_none()
    exchange = asset.exchange.value if asset else "NASDAQ"

    from app.agents.workflow import run_technical_workflow
    technical_result = await run_technical_workflow(
        symbol=rec.symbol,
        exchange=exchange,
        user_id=current_user.id,
        fallback_price=float(rec.current_price_at_recommendation) if rec.current_price_at_recommendation else None,
    )

    ta = technical_result.get("technical_analysis")
    if ta:
        rec.technical_analysis = ta
        await db.flush()
        await db.commit()
        # Feed the shared alerting core: if this on-demand analysis caught a
        # signal flip the 30-min sampler missed, holders still get notified.
        try:
            from app.workers.in_process_scheduler import process_signal_transition
            await process_signal_transition(rec.symbol, ta)
        except Exception as alert_exc:
            logger.warning("on-demand signal alert failed", symbol=rec.symbol, error=str(alert_exc))

    return {
        "message": "Technical analysis completed",
        "technical_analysis": ta,
    }


@router.post("/{recommendation_id}/recompute-quant-models")
async def recompute_quant_models(
    recommendation_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Compute (or recompute) quantitative financial models for an existing recommendation.
    Fetches fresh market data, runs DCF / DDM / Monte Carlo / Comps / Sensitivity,
    and merges the result into the recommendation's fundamental_analysis JSON.
    """
    result = await db.execute(
        select(Recommendation).where(Recommendation.id == recommendation_id)
    )
    rec = result.scalar_one_or_none()

    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")

    if not rec.fundamental_analysis:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fundamental analysis stored — run full analysis first",
        )

    # Fetch market data to supply to the quant model engine
    from app.services.market_data.yahoo_service import YahooFinanceService
    from app.agents.fundamental.agent import get_fundamental_agent
    import requests as _req

    yahoo = YahooFinanceService()
    market_data = await yahoo.get_stock_info(rec.symbol, force_refresh=True) or {}

    # On Railway, Yahoo returns price via fast_info but ticker.info is blocked,
    # so fundamentals (P/E, FCF, sector, market_cap) are all missing.
    # Strategy: try v10/quoteSummary directly (same domain as working v8/chart),
    # then fall back to Alpha Vantage.
    def _rv(d: dict, key: str):
        val = d.get(key)
        return (val.get("raw") if isinstance(val, dict) else val) if val else None

    missing_fundamentals = (
        not market_data.get("pe_ratio")
        or not market_data.get("sector")
        or not market_data.get("market_cap")
    )

    if missing_fundamentals:
        # ── Attempt 1: Yahoo v10 quoteSummary with browser headers ──────────
        try:
            v10_resp = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: _req.get(
                    f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{rec.symbol}",
                    params={"modules": "financialData,defaultKeyStatistics,summaryProfile,summaryDetail"},
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"},
                    timeout=10,
                )
            )
            if v10_resp.status_code == 200:
                qs = (v10_resp.json().get("quoteSummary") or {}).get("result") or []
                if qs:
                    fd = qs[0].get("financialData") or {}
                    ks = qs[0].get("defaultKeyStatistics") or {}
                    sp = qs[0].get("summaryProfile") or {}
                    sd = qs[0].get("summaryDetail") or {}
                    candidates = {
                        "pe_ratio":       _rv(ks, "trailingPE") or _rv(sd, "trailingPE"),
                        "forward_pe":     _rv(ks, "forwardPE"),
                        "price_to_book":  _rv(ks, "priceToBook"),
                        "price_to_sales": _rv(sd, "priceToSalesTrailing12Months"),
                        "beta":           _rv(ks, "beta"),
                        "market_cap":     _rv(ks, "marketCap"),
                        "free_cash_flow": _rv(fd, "freeCashflow"),
                        "revenue_growth": _rv(fd, "revenueGrowth"),
                        "earnings_growth":_rv(fd, "earningsGrowth"),
                        "roe":            _rv(fd, "returnOnEquity"),
                        "dividend_yield": _rv(sd, "dividendYield"),
                        "sector":         sp.get("sector"),
                    }
                    filled = {k: v for k, v in candidates.items() if v is not None}
                    # Merge: Yahoo's real values (non-zero, non-None) take priority
                    for k, v in filled.items():
                        if not market_data.get(k):
                            market_data[k] = v
                    logger.info(
                        "v10 quoteSummary supplemented market data",
                        symbol=rec.symbol, fields=list(filled.keys()),
                    )
                    missing_fundamentals = (
                        not market_data.get("pe_ratio")
                        or not market_data.get("sector")
                        or not market_data.get("market_cap")
                    )
        except Exception as exc:
            logger.warning("v10 quoteSummary failed", symbol=rec.symbol, error=str(exc))

    if missing_fundamentals:
        # ── Attempt 2: Alpha Vantage OVERVIEW ───────────────────────────────
        existing_price = float(market_data.get("price") or rec.current_price_at_recommendation or 0)
        av_data = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: yahoo._fetch_alpha_vantage_info(rec.symbol, existing_price=existing_price)
        )
        if av_data:
            for k, v in av_data.items():
                if v is not None and not market_data.get(k):
                    market_data[k] = v
            logger.info("Alpha Vantage supplemented market data", symbol=rec.symbol)

    if not market_data.get("price"):
        market_data["price"] = float(rec.current_price_at_recommendation or 0)

    market_data["symbol"] = rec.symbol
    logger.info(
        "Final market data for quant models",
        symbol=rec.symbol,
        price=market_data.get("price"),
        pe=market_data.get("pe_ratio"),
        fcf=market_data.get("free_cash_flow"),
        market_cap=market_data.get("market_cap"),
        sector=market_data.get("sector"),
    )

    # Run quantitative models only (no LLM call)
    agent = get_fundamental_agent()
    quant_models = agent._compute_financial_models(market_data)

    # Merge into fundamental_analysis JSON (copy-on-write for SQLAlchemy JSON column)
    fa = dict(rec.fundamental_analysis)
    fa["quantitative_models"] = quant_models
    rec.fundamental_analysis = fa

    await db.flush()
    await db.commit()

    logger.info(
        "Quantitative models recomputed",
        recommendation_id=recommendation_id,
        symbol=rec.symbol,
        models=list(quant_models.keys()),
    )

    return {
        "message": "Quantitative models computed",
        "quantitative_models": quant_models,
    }
