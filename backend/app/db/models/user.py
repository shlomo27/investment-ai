import enum
from datetime import datetime, timezone
from sqlalchemy import String, Float, Integer, Boolean, DateTime, Enum as SAEnum, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class RiskProfile(str, enum.Enum):
    CONSERVATIVE = "CONSERVATIVE"
    PASSIVE = "PASSIVE"
    AGGRESSIVE = "AGGRESSIVE"
    HYBRID = "HYBRID"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    risk_profile: Mapped[RiskProfile] = mapped_column(
        SAEnum(RiskProfile), nullable=False, default=RiskProfile.PASSIVE
    )
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=50)  # 0-100
    cash_balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_single_asset_exposure: Mapped[float] = mapped_column(Float, nullable=False, default=0.03)

    # Extended risk profile fields
    age_group: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "18-25" | "26-35" | "36-50" | "50+"
    investment_horizon_months: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 3 | 6 | 12 | 36 | 60 | 120

    # Investment preferences (set during onboarding)
    investment_type: Mapped[str] = mapped_column(String(10), nullable=False, default="BOTH")  # STOCKS | ETFS | BOTH
    allows_volatile: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allows_leveraged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allows_short: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_onboarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(10), default="he", nullable=False)
    push_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notification_email: Mapped[bool] = mapped_column(Boolean, default=True)
    notification_sms: Mapped[bool] = mapped_column(Boolean, default=True)
    notification_push: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    portfolio_items = relationship("Portfolio", back_populates="user", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    watchlist_items = relationship("Watchlist", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, risk_profile={self.risk_profile})>"

    @property
    def total_portfolio_value(self) -> float:
        return sum(item.current_value for item in self.portfolio_items if item.current_value)

    @property
    def total_value_with_cash(self) -> float:
        return self.total_portfolio_value + self.cash_balance
