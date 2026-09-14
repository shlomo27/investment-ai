"""
Subscription billing — RevenueCat webhook and subscription status.

Apple and Google are the source of truth for whether a subscription is paid.
RevenueCat sits in front of both: it validates receipts, normalises the two
stores' very different event models, and posts the result here. That is why
this file contains no receipt parsing — trusting a receipt the client hands
us would mean trusting the client about whether it paid.

The webhook is the ONLY path that grants a store entitlement. The app never
tells the server what tier it is; it asks.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.entitlements import entitlements_for
from app.core.security import get_current_active_user
from app.db.models.user import User, SubscriptionTier, SubscriptionSource

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/billing", tags=["Billing"])


# RevenueCat event types that GRANT or EXTEND access.
_GRANTING = {
    "INITIAL_PURCHASE",
    "RENEWAL",
    "UNCANCELLATION",
    "PRODUCT_CHANGE",
    "NON_RENEWING_PURCHASE",
    "SUBSCRIPTION_EXTENDED",
}

# Events that REVOKE access immediately.
#
# CANCELLATION is deliberately NOT here. It means the user switched off
# auto-renew — they have paid through the end of the current period and are
# entitled to every day of it. Revoking on cancellation would cut off someone
# who is still a paying customer, which is both wrong and a refund request.
# EXPIRATION is the event that actually ends access.
_REVOKING = {"EXPIRATION"}

_STORE_TO_SOURCE = {
    "APP_STORE": SubscriptionSource.APPLE,
    "MAC_APP_STORE": SubscriptionSource.APPLE,
    "PLAY_STORE": SubscriptionSource.GOOGLE,
}


class SubscriptionStatus(BaseModel):
    tier: str
    is_pro: bool
    expires_at: Optional[datetime] = None
    source: Optional[str] = None
    watchlist_limit: Optional[int] = None
    recommendation_limit: Optional[int] = None
    full_research: bool = False


@router.get("/status", response_model=SubscriptionStatus)
async def subscription_status(
    current_user: User = Depends(get_current_active_user),
):
    """What this account is entitled to right now.

    The app calls this after a purchase completes and on resume. It reads the
    server's view, never the store SDK's — the SDK on the device can be
    optimistic, restored from another account, or simply stale.
    """
    ent = entitlements_for(current_user)
    return SubscriptionStatus(
        tier=ent.tier,
        is_pro=ent.tier == "PRO",
        expires_at=current_user.subscription_expires_at,
        source=(
            current_user.subscription_source.value
            if current_user.subscription_source
            else None
        ),
        watchlist_limit=ent.watchlist_limit,
        recommendation_limit=ent.recommendation_limit,
        full_research=ent.full_research,
    )


def _resolve_user_id(app_user_id: Optional[str]) -> Optional[int]:
    """Our user id out of RevenueCat's app_user_id.

    The client calls Purchases.logIn() with the numeric user id, so the value
    should be an integer. RevenueCat also issues its own anonymous ids of the
    form "$RCAnonymousID:abc123" before login; those belong to no account here
    and are skipped rather than guessed at.
    """
    if not app_user_id or app_user_id.startswith("$RCAnonymousID"):
        return None
    try:
        return int(app_user_id)
    except ValueError:
        return None


def _expiry_from(event: Dict[str, Any]) -> Optional[datetime]:
    """Period end as a timezone-aware datetime.

    RevenueCat sends epoch milliseconds. A naive datetime here would compare
    incorrectly against the aware value in User.is_pro and silently misjudge
    whether a subscription is live.
    """
    ms = event.get("expiration_at_ms") or event.get("expires_date_ms")
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


@router.post("/webhook/revenuecat", include_in_schema=False)
async def revenuecat_webhook(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Apply a subscription event from RevenueCat.

    Returns 200 for anything understood, including events about users we do
    not have. RevenueCat retries non-2xx responses with backoff, so answering
    4xx to an event that is simply irrelevant would have it redelivered for
    hours.
    """
    secret = getattr(settings, "REVENUECAT_WEBHOOK_SECRET", "") or ""
    if not secret:
        # Refuse rather than accept unauthenticated subscription changes: this
        # endpoint grants paid access, so an open version of it is a free
        # subscription for anyone who finds the URL.
        logger.error("RevenueCat webhook called but REVENUECAT_WEBHOOK_SECRET is unset")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing webhook is not configured",
        )

    # RevenueCat sends the configured value verbatim in the Authorization
    # header. Compared in constant time so the secret cannot be recovered by
    # timing repeated requests.
    import hmac

    if not authorization or not hmac.compare_digest(authorization, secret):
        logger.warning("RevenueCat webhook rejected — bad Authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
        )

    body = await request.json()
    event = body.get("event") or {}
    event_type = (event.get("type") or "").upper()
    app_user_id = event.get("app_user_id")

    user_id = _resolve_user_id(app_user_id)
    if user_id is None:
        logger.info("RevenueCat event for unmapped app_user_id", app_user_id=app_user_id, type=event_type)
        return {"ok": True, "ignored": "unmapped_app_user_id"}

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        logger.info("RevenueCat event for unknown user", user_id=user_id, type=event_type)
        return {"ok": True, "ignored": "unknown_user"}

    # TRANSFER moves an entitlement between accounts — the receiving account is
    # handled by its own event, so here we only give up the one that lost it.
    if event_type == "TRANSFER":
        transferred_from = event.get("transferred_from") or []
        if str(user_id) in [str(x) for x in transferred_from]:
            user.subscription_tier = SubscriptionTier.FREE
            user.subscription_expires_at = None
            await db.commit()
            logger.info("Subscription transferred away", user_id=user_id)
        return {"ok": True}

    if event_type in _GRANTING:
        expires = _expiry_from(event)
        # A grant with no period end from a store is not trustworthy — the
        # account would become permanently PRO on a single event. Treat it as
        # unparseable rather than as "forever".
        if expires is None and event_type != "NON_RENEWING_PURCHASE":
            logger.warning(
                "Granting event without an expiry — ignored",
                user_id=user_id, type=event_type,
            )
            return {"ok": True, "ignored": "no_expiry"}

        # Never shorten an existing entitlement. Events can arrive out of order
        # after a retry, and applying an older RENEWAL after a newer one would
        # move the expiry backwards and cut off a paying user.
        current = user.subscription_expires_at
        if expires and current and current > expires:
            logger.info(
                "Ignoring out-of-order event with earlier expiry",
                user_id=user_id, type=event_type,
            )
            return {"ok": True, "ignored": "stale_event"}

        user.subscription_tier = SubscriptionTier.PRO
        user.subscription_expires_at = expires
        user.subscription_source = _STORE_TO_SOURCE.get(
            (event.get("store") or "").upper()
        )
        if app_user_id:
            user.billing_customer_id = str(app_user_id)[:128]
        await db.commit()
        logger.info(
            "Subscription granted", user_id=user_id, type=event_type, expires=expires
        )
        return {"ok": True}

    if event_type in _REVOKING:
        user.subscription_tier = SubscriptionTier.FREE
        # The expiry is kept rather than cleared: it is the record of when
        # access actually ended, and win-back messaging needs it.
        await db.commit()
        logger.info("Subscription revoked", user_id=user_id, type=event_type)
        return {"ok": True}

    # CANCELLATION, BILLING_ISSUE, SUBSCRIBER_ALIAS and anything RevenueCat
    # adds later: recorded, no entitlement change. Access ends at EXPIRATION.
    logger.info("RevenueCat event noted", user_id=user_id, type=event_type)
    return {"ok": True}
