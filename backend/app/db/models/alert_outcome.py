"""What happened after each alert.

Whether the technical signal is worth anything cannot be judged from one
stock. BMRN was called a buy three times on its way down 16%, and that is an
anecdote; the question is how often the alerts are right, by kind, measured
the same way every time. Each alert records the price it went out at, and a
daily job fills in the price about a week and about a month later.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class AlertOutcome(Base):
    __tablename__ = "alert_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    #: TA (a technical signal change), ENTRY (technical BUY meeting a live,
    #: confident BUY recommendation), STOP or TARGET (a recommendation level
    #: reached at the close).
    kind: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    #: The signal the alert announced: BUY_NOW, SELL_NOW, WAIT, STOP, TARGET...
    signal: Mapped[str] = mapped_column(String(20), nullable=False)
    price_at_alert: Mapped[float] = mapped_column(Float, nullable=False)
    recommendation_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    #: Price about five trading days (seven calendar days) later.
    price_1w: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    #: Price about twenty trading days (twenty-eight calendar days) later.
    price_1m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
