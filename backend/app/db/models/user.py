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


class AlertFrequency(str, enum.Enum):
    """How often external alerts (push/SMS/email) reach the user.
    In-app inbox always receives everything in real time."""
    REALTIME = "REALTIME"            # every alert immediately
    EVERY_4_HOURS = "EVERY_4_HOURS"  # one digest summary per 4h window
    DAILY = "DAILY"                  # one digest summary per day


class SubscriptionTier(str, enum.Enum):
    """What the account is entitled to.

    FREE is a real, permanent tier rather than a trial — the marginal cost of
    a free user is close to zero, because analyses are produced per stock and
    shared by every account, not generated per user. What FREE limits is
    breadth: how many stocks can be followed and how many recommendations are
    visible.
    """
    FREE = "FREE"
    PRO = "PRO"


class SubscriptionSource(str, enum.Enum):
    """Where an entitlement came from — it decides who can revoke it.

    Store subscriptions are owned by Apple and Google: they renew, lapse and
    refund outside this system, so their expiry is authoritative and must
    never be edited here. MANUAL is for accounts granted access directly
    (a reviewer, a pilot customer, staff) and is the only source this system
    may set on its own.
    """
    APPLE = "APPLE"
    GOOGLE = "GOOGLE"
    MANUAL = "MANUAL"


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

    # ── Terms acceptance ────────────────────────────────────────────────────
    # Evidence, not a flag. For a service publishing investment analysis, "the
    # user accepted the risk disclosure" has to be answerable with when, and
    # with which wording — a bare boolean cannot tell today's text from last
    # year's.
    accepted_terms_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_terms_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # ── Subscription ────────────────────────────────────────────────────────
    subscription_tier: Mapped[SubscriptionTier] = mapped_column(
        SAEnum(SubscriptionTier, name="subscriptiontier"),
        default=SubscriptionTier.FREE,
        server_default=SubscriptionTier.FREE.value,
        nullable=False,
    )
    # NULL means "no expiry" and is only valid for MANUAL grants. A store
    # subscription always carries the period end the store reported, so a
    # lapsed renewal downgrades the account on its own instead of leaving a
    # paid tier that nobody is paying for.
    subscription_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    subscription_source: Mapped[SubscriptionSource | None] = mapped_column(
        SAEnum(SubscriptionSource, name="subscriptionsource"), nullable=True
    )
    # RevenueCat's identifier for this user, so a purchase made on one device
    # restores on the next one. Kept even after a subscription lapses.
    billing_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    preferred_language: Mapped[str] = mapped_column(String(10), default="he", nullable=False)
    push_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Personal Telegram chat (private bot conversation) — linked from Settings;
    # personal alerts go here with full detail, unlike generic email/push/SMS
    telegram_chat_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Whether an account has actually been used. Creation was the only recorded
    # moment in an account's life, so "credentials were sent" and "they logged
    # in" were indistinguishable.
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notification_email: Mapped[bool] = mapped_column(Boolean, default=True)
    notification_sms: Mapped[bool] = mapped_column(Boolean, default=True)
    notification_push: Mapped[bool] = mapped_column(Boolean, default=True)
    # External alert cadence (REALTIME | EVERY_4_HOURS | DAILY); inbox unaffected
    alert_frequency: Mapped[str] = mapped_column(String(20), nullable=False, default="REALTIME")
    last_digest_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    @property
    def is_pro(self) -> bool:
        """Whether PRO entitlements are live right now.

        Expiry is checked on read rather than by a scheduled downgrade job:
        a job that fails to run would silently keep lapsed accounts paid, and
        this comparison costs nothing.
        """
        if self.subscription_tier != SubscriptionTier.PRO:
            return False
        if self.subscription_expires_at is None:
            # Only MANUAL grants are allowed to be open-ended.
            return self.subscription_source == SubscriptionSource.MANUAL
        return self.subscription_expires_at > datetime.now(timezone.utc)

    @property
    def telegram_linked(self) -> bool:
        return bool(self.telegram_chat_id)

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
