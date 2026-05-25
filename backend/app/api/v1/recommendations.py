"""
Recommendations API routes - the "Inbox" that users see after login
GET /recommendations, GET /recommendations/{id}, POST /recommendations/{id}/acknowledge
GET /inbox (notification inbox with full AI details)
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.database import get_db
from app.core.security import get_current_active_user
from app.db.models.user import User
from app.db.models.recommendation import Recommendation, RecommendationStatus, RecommendationType
from app.db.models.notification import Notification, NotificationType
from app.db.models.asset import Asset

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
    asset_name: Optional[str]
    sector: Optional[str]
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

    class Config:
        from_attributes = True


@router.get("/", response_model=List[RecommendationResponse])
async def get_recommendations(
    status_filter: Optional[str] = None,
    limit: int = 20,
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
        ])
    )

    if status_filter:
        try:
            status_enum = RecommendationStatus(status_filter.upper())
            query = select(Recommendation).where(Recommendation.status == status_enum)
        except ValueError:
            pass

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
            asset_name=asset.name if asset else None,
            sector=asset.sector if asset else None,
            created_at=rec.created_at,
            approved_at=rec.approved_at,
            presented_at=rec.presented_at,
        ))

    return response


@router.get("/inbox", response_model=List[NotificationInboxResponse])
async def get_inbox(
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    The main notification inbox. Authenticated users see full internal details here.
    This is the only place where the full AI analysis is exposed.
    """
    query = select(Notification).where(Notification.user_id == current_user.id)

    if unread_only:
        query = query.where(Notification.is_read == False)

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

    return [NotificationInboxResponse.from_orm(n) for n in notifications]


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
        asset_name=asset.name if asset else None,
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
    )

    if technical_result.get("technical_analysis"):
        rec.technical_analysis = technical_result["technical_analysis"]
        await db.flush()

    return {
        "message": "Technical analysis completed",
        "technical_analysis": technical_result.get("technical_analysis"),
    }
