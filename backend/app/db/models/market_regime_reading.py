"""One row per daily market reading.

The regime alone (Redis) answers "what is the market now". The Market screen
also needs "how did we get here": the history of readings for its charts,
and the moments the regime changed, so it can show what the index did after
each change — the plainest test of whether the detector sees anything.
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class MarketRegimeReading(Base):
    __tablename__ = "market_regime_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    #: What this reading scored, before confirmation.
    reading: Mapped[str] = mapped_column(String(12), nullable=False)
    #: The regime in force after this reading (the one users were told).
    committed: Mapped[str] = mapped_column(String(12), nullable=False)
    #: True on the reading that confirmed a change of regime.
    changed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: The full reading: layers, reasons, inputs.
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
