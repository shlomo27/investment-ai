from datetime import datetime
from sqlalchemy import String, Float, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("assets.id", ondelete="SET NULL"), nullable=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_buy_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    current_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    current_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pnl_percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    exposure_percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    user = relationship("User", back_populates="portfolio_items")
    asset = relationship("Asset", back_populates="portfolio_items")

    def update_metrics(self, current_price: float, total_portfolio_value: float) -> None:
        self.current_price = current_price
        self.current_value = self.quantity * current_price
        self.pnl = self.current_value - (self.quantity * self.avg_buy_price)
        self.pnl_percentage = (
            ((self.current_price - self.avg_buy_price) / self.avg_buy_price) * 100
            if self.avg_buy_price > 0 else 0.0
        )
        self.exposure_percentage = (
            (self.current_value / total_portfolio_value) * 100
            if total_portfolio_value > 0 else 0.0
        )

    def __repr__(self) -> str:
        return f"<Portfolio(user_id={self.user_id}, symbol={self.symbol}, qty={self.quantity})>"
