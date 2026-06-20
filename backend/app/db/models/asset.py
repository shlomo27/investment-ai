import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Integer, Boolean, DateTime, Enum as SAEnum, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Exchange(str, enum.Enum):
    NASDAQ = "NASDAQ"
    NYSE = "NYSE"
    TASE = "TASE"
    AMEX = "AMEX"
    LSE = "LSE"
    EURONEXT = "EURONEXT"
    OTHER = "OTHER"


class AssetType(str, enum.Enum):
    STOCK = "STOCK"
    ETF = "ETF"
    BOND = "BOND"
    CRYPTO = "CRYPTO"
    COMMODITY = "COMMODITY"


class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class CapTier(str, enum.Enum):
    LARGE = "LARGE"    # >$10B
    MID = "MID"        # $2B–$10B
    SMALL = "SMALL"    # $300M–$2B
    MICRO = "MICRO"    # <$300M


class DirectionBias(str, enum.Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_hebrew: Mapped[str | None] = mapped_column(String(255), nullable=True)
    exchange: Mapped[Exchange] = mapped_column(SAEnum(Exchange), nullable=False, default=Exchange.NASDAQ)
    asset_type: Mapped[AssetType] = mapped_column(SAEnum(AssetType), nullable=False, default=AssetType.STOCK)
    is_active_in_pool: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    risk_level: Mapped[RiskLevel] = mapped_column(SAEnum(RiskLevel), nullable=False, default=RiskLevel.MEDIUM)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str] = mapped_column(String(50), nullable=False, default="US")
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    pe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_yield: Mapped[float | None] = mapped_column(Float, nullable=True)
    beta: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    fundamental_score: Mapped[float] = mapped_column(Float, default=50.0, nullable=False)
    technical_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Universe / screener fields
    cap_tier: Mapped[str] = mapped_column(String(10), nullable=False, default="LARGE")  # LARGE/MID/SMALL/MICRO
    in_universe: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    direction_bias: Mapped[str] = mapped_column(String(10), nullable=False, default="NEUTRAL")  # LONG/SHORT/NEUTRAL
    long_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)   # 0-100 screener score
    short_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)  # 0-100 screener score
    screener_activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    added_to_pool_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    removed_from_pool_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    portfolio_items = relationship("Portfolio", back_populates="asset")
    recommendations = relationship("Recommendation", back_populates="asset")
    watchlist_items = relationship("Watchlist", back_populates="asset")

    def __repr__(self) -> str:
        return f"<Asset(symbol={self.symbol}, exchange={self.exchange}, active={self.is_active_in_pool})>"
