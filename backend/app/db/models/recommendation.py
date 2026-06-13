import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Integer, ForeignKey, DateTime, Enum as SAEnum, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class RecommendationType(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    STRONG_BUY = "STRONG_BUY"
    STRONG_SELL = "STRONG_SELL"


class RecommendationStatus(str, enum.Enum):
    PENDING_SENIOR_REVIEW = "PENDING_SENIOR_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PRESENTED_TO_USER = "PRESENTED_TO_USER"
    ACTIONED = "ACTIONED"
    DISMISSED = "DISMISSED"


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    recommendation_type: Mapped[RecommendationType] = mapped_column(SAEnum(RecommendationType), nullable=False)
    status: Mapped[RecommendationStatus] = mapped_column(
        SAEnum(RecommendationStatus), nullable=False, default=RecommendationStatus.PENDING_SENIOR_REVIEW
    )
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # 0-100
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_price_at_recommendation: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Raw data from הפקיד (Data Fetcher Agent)
    data_fetcher_raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Fundamental Analysis
    fundamental_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fundamental_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Sentiment Data
    sentiment_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Senior Committee Review
    senior_review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    senior_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    senior_approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # What triggered this scan
    trigger_type: Mapped[str | None] = mapped_column(String(50), nullable=True, default="SCHEDULED")
    trigger_details: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Technical Analysis (optional, on-demand)
    technical_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    technical_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Risk metrics
    risk_factors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    expected_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    presented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    asset = relationship("Asset", back_populates="recommendations")
    notifications = relationship("Notification", back_populates="recommendation")
    orders = relationship("Order", back_populates="recommendation")

    def __repr__(self) -> str:
        return f"<Recommendation(id={self.id}, symbol={self.symbol}, type={self.recommendation_type}, status={self.status})>"
