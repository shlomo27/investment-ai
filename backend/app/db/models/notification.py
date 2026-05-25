import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Integer, ForeignKey, DateTime, Enum as SAEnum, Text, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class NotificationType(str, enum.Enum):
    RECOMMENDATION = "RECOMMENDATION"
    ALERT = "ALERT"
    SYSTEM = "SYSTEM"
    RISK_WARNING = "RISK_WARNING"
    PRICE_TARGET = "PRICE_TARGET"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recommendation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("recommendations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        SAEnum(NotificationType), nullable=False, default=NotificationType.RECOMMENDATION
    )
    # Generic safe message for push/SMS - never exposes AI analysis
    external_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="יש לך עדכון השקעות חדש. אנא היכנס למערכת לצפייה בפרטים."
    )
    # Full internal detail - only visible after login
    internal_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    channels_sent: Mapped[list | None] = mapped_column(JSON, nullable=True)  # ["push", "sms", "email"]
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="notifications")
    recommendation = relationship("Recommendation", back_populates="notifications")

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, user_id={self.user_id}, type={self.notification_type}, read={self.is_read})>"
