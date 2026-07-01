from datetime import datetime
from sqlalchemy import Integer, Float, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class PortfolioHistory(Base):
    __tablename__ = "portfolio_history"
    __table_args__ = (
        UniqueConstraint("user_id", "snapshot_date", name="uq_portfolio_history_user_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    total_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cash_balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    market_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_pnl_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")

    def __repr__(self) -> str:
        return f"<PortfolioHistory(user_id={self.user_id}, date={self.snapshot_date}, total={self.total_value})>"
