from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Integer, ForeignKey, DateTime, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Watchlist(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    asset_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    alert_on_technical_signal: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_technical_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_signal_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Price alert fields
    alert_price_above: Mapped[float | None] = mapped_column(Float, nullable=True)
    alert_price_below: Mapped[float | None] = mapped_column(Float, nullable=True)
    alert_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="watchlist_items")
    asset = relationship("Asset", back_populates="watchlist_items")

    def __repr__(self) -> str:
        return f"<Watchlist(user_id={self.user_id}, symbol={self.symbol})>"
