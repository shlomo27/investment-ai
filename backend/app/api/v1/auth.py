"""
Authentication API routes
POST /register, POST /login, POST /logout, GET /me, PUT /profile
"""
from datetime import datetime, timezone
from typing import List, Optional
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field, validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import (
    verify_password,
    get_password_hash,
    create_token_pair,
    create_pre_auth_token,
    verify_pre_auth_token,
    verify_token,
    get_current_active_user,
    Token,
)
from app.db.models.user import User, RiskProfile

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


# ─── Request/Response Schemas ──────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)
    phone: Optional[str] = None
    preferred_language: str = "he"

    @validator("password")
    def validate_password(cls, v):
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    risk_profile: Optional[RiskProfile] = None
    risk_score: Optional[int] = Field(None, ge=0, le=100)
    preferred_language: Optional[str] = None
    notification_email: Optional[bool] = None
    notification_sms: Optional[bool] = None
    notification_push: Optional[bool] = None
    max_single_asset_exposure: Optional[float] = Field(None, ge=0.005, le=0.25)
    push_token: Optional[str] = None
    age_group: Optional[str] = None
    investment_horizon_months: Optional[int] = None
    allows_short: Optional[bool] = None
    allows_volatile: Optional[bool] = None
    alert_frequency: Optional[str] = None  # REALTIME | EVERY_4_HOURS | DAILY

    @validator("alert_frequency")
    def _validate_alert_frequency(cls, v):
        if v is not None and v not in ("REALTIME", "EVERY_4_HOURS", "DAILY"):
            raise ValueError("alert_frequency must be REALTIME, EVERY_4_HOURS or DAILY")
        return v


class OnboardingRequest(BaseModel):
    risk_profile: RiskProfile
    risk_score: int = Field(ge=0, le=100)
    investment_type: str = "BOTH"          # STOCKS | ETFS | BOTH
    allows_volatile: bool = False
    allows_leveraged: bool = False
    allows_short: bool = False
    notification_email: bool = True
    notification_sms: bool = True
    notification_push: bool = True


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    phone: Optional[str]
    risk_profile: RiskProfile
    risk_score: int
    cash_balance: float
    max_single_asset_exposure: float
    investment_type: str = "BOTH"
    allows_volatile: bool = False
    allows_leveraged: bool = False
    allows_short: bool = False
    is_active: bool
    is_onboarded: bool
    is_admin: bool
    preferred_language: str
    notification_email: bool
    notification_sms: bool
    notification_push: bool
    created_at: datetime
    age_group: Optional[str] = None
    investment_horizon_months: Optional[int] = None
    alert_frequency: str = "REALTIME"
    totp_enabled: bool = False
    telegram_linked: bool = False

    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    user: UserResponse
    tokens: Token


# ─── Routes ────────────────────────────────────────────────────────────────────

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user account."""
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == request.email.lower()))
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(
        email=request.email.lower(),
        hashed_password=get_password_hash(request.password),
        full_name=request.full_name.strip(),
        phone=request.phone,
        preferred_language=request.preferred_language,
        risk_profile=RiskProfile.PASSIVE,
        risk_score=50,
        cash_balance=0.0,
        is_active=True,
        is_onboarded=False,
    )
    db.add(user)
    await db.flush()

    tokens = create_token_pair(user.id, user.email)

    logger.info("New user registered", user_id=user.id, email=user.email)

    return AuthResponse(
        user=UserResponse.from_orm(user),
        tokens=tokens,
    )


async def _login_lockout_check(email: str):
    """Brute-force guard: after 8 failed attempts, lock the email for 15 min."""
    from app.core.config import settings
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL)
        try:
            n = int(await r.get(f"investment_ai:login_fail:{email}") or 0)
            if n >= 8:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="יותר מדי ניסיונות התחברות. נסה שוב בעוד 15 דקות.",
                )
        finally:
            await r.aclose()
    except HTTPException:
        raise
    except Exception:
        pass  # redis down — don't block logins


async def _login_fail_record(email: str):
    from app.core.config import settings
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL)
        try:
            k = f"investment_ai:login_fail:{email}"
            await r.incr(k)
            await r.expire(k, 15 * 60)
        finally:
            await r.aclose()
    except Exception:
        pass


async def _login_fail_clear(email: str):
    from app.core.config import settings
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL)
        try:
            await r.delete(f"investment_ai:login_fail:{email}")
        finally:
            await r.aclose()
    except Exception:
        pass


@router.post("/login", response_model=AuthResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Login with email and password."""
    email = request.email.lower()
    await _login_lockout_check(email)
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(request.password, user.hashed_password):
        await _login_fail_record(email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    await _login_fail_clear(email)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    # If 2FA is enabled, return a pre-auth token instead of full tokens
    if getattr(user, "totp_enabled", False):
        pre_auth = create_pre_auth_token(user.id)
        logger.info("2FA required for login", user_id=user.id)
        return {"requires_2fa": True, "pre_auth_token": pre_auth}

    tokens = create_token_pair(user.id, user.email)
    logger.info("User logged in", user_id=user.id, email=user.email)

    return AuthResponse(
        user=UserResponse.from_orm(user),
        tokens=tokens,
    )


@router.post("/token", response_model=Token)
async def login_form(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """OAuth2 form-based login (for Swagger UI)."""
    result = await db.execute(select(User).where(User.email == form_data.username.lower()))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return create_token_pair(user.id, user.email)


@router.post("/refresh", response_model=Token)
async def refresh_token(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token using refresh token (sent in JSON body)."""
    token_data = verify_token(body.refresh_token, token_type="refresh")

    result = await db.execute(select(User).where(User.id == token_data.user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return create_token_pair(user.id, user.email)


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_active_user)):
    """Logout endpoint (client should discard tokens)."""
    logger.info("User logged out", user_id=current_user.id)
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_active_user)):
    """Get current user profile."""
    return UserResponse.from_orm(current_user)


@router.put("/profile", response_model=UserResponse)
async def update_profile(
    request: ProfileUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user profile settings."""
    if request.full_name is not None:
        current_user.full_name = request.full_name.strip()
    if request.phone is not None:
        current_user.phone = request.phone
    if request.risk_profile is not None:
        current_user.risk_profile = request.risk_profile
    if request.risk_score is not None:
        current_user.risk_score = request.risk_score
    if request.preferred_language is not None:
        current_user.preferred_language = request.preferred_language
    if request.notification_email is not None:
        current_user.notification_email = request.notification_email
    if request.notification_sms is not None:
        current_user.notification_sms = request.notification_sms
    if request.notification_push is not None:
        current_user.notification_push = request.notification_push
    if request.max_single_asset_exposure is not None:
        current_user.max_single_asset_exposure = request.max_single_asset_exposure
    if request.push_token is not None:
        current_user.push_token = request.push_token
    if request.age_group is not None:
        current_user.age_group = request.age_group
    if request.investment_horizon_months is not None:
        current_user.investment_horizon_months = request.investment_horizon_months
    if request.allows_short is not None:
        current_user.allows_short = request.allows_short
    if request.allows_volatile is not None:
        current_user.allows_volatile = request.allows_volatile
    if request.alert_frequency is not None:
        current_user.alert_frequency = request.alert_frequency

    await db.flush()
    logger.info("Profile updated", user_id=current_user.id)

    return UserResponse.from_orm(current_user)


@router.post("/onboarding", response_model=UserResponse)
async def complete_onboarding(
    request: OnboardingRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Complete the onboarding process."""
    if current_user.is_onboarded:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already onboarded",
        )

    current_user.risk_profile = request.risk_profile
    current_user.risk_score = request.risk_score
    current_user.investment_type = request.investment_type
    current_user.allows_volatile = request.allows_volatile
    current_user.allows_leveraged = request.allows_leveraged
    current_user.allows_short = request.allows_short
    current_user.notification_email = request.notification_email
    current_user.notification_sms = request.notification_sms
    current_user.notification_push = request.notification_push
    current_user.is_onboarded = True

    await db.flush()

    logger.info(
        "Onboarding completed",
        user_id=current_user.id,
        risk_profile=request.risk_profile,
        investment_type=request.investment_type,
    )

    return UserResponse.from_orm(current_user)


@router.post("/2fa/setup")
async def setup_2fa(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate TOTP secret and QR code for 2FA setup. Does not enable 2FA yet."""
    import pyotp
    import qrcode
    import io
    import base64

    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    otp_uri = totp.provisioning_uri(name=current_user.email, issuer_name="Investment AI")

    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(otp_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_b64 = base64.b64encode(buffer.getvalue()).decode()

    current_user.totp_secret = secret
    await db.flush()

    return {
        "secret": secret,
        "otp_uri": otp_uri,
        "qr_code": f"data:image/png;base64,{qr_b64}",
    }


@router.post("/2fa/enable")
async def enable_2fa(
    code: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify TOTP code and permanently enable 2FA on this account."""
    import pyotp

    if not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="Run /auth/2fa/setup first")

    if not pyotp.TOTP(current_user.totp_secret).verify(code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid verification code")

    current_user.totp_enabled = True
    await db.flush()
    logger.info("2FA enabled", user_id=current_user.id)
    return {"enabled": True, "message": "Two-factor authentication is now active"}


@router.post("/2fa/disable")
async def disable_2fa(
    code: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Disable 2FA after verifying the current TOTP code."""
    import pyotp

    if not current_user.totp_enabled or not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="2FA is not enabled")

    if not pyotp.TOTP(current_user.totp_secret).verify(code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid verification code")

    current_user.totp_enabled = False
    current_user.totp_secret = None
    await db.flush()
    logger.info("2FA disabled", user_id=current_user.id)
    return {"disabled": True, "message": "Two-factor authentication has been disabled"}


@router.post("/2fa/login")
async def complete_2fa_login(
    pre_auth_token: str,
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """Complete login after password verification: supply pre_auth_token + TOTP code."""
    import pyotp

    user_id = verify_pre_auth_token(pre_auth_token)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid session")

    if not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status_code=400, detail="2FA not configured for this user")

    if not pyotp.TOTP(user.totp_secret).verify(code, valid_window=1):
        raise HTTPException(status_code=401, detail="Invalid or expired 2FA code")

    tokens = create_token_pair(user.id, user.email)
    logger.info("2FA login successful", user_id=user.id)

    return AuthResponse(user=UserResponse.from_orm(user), tokens=tokens)

# ─── Personal Telegram linking ─────────────────────────────────────────────────

class TelegramLinkResponse(BaseModel):
    link: str
    expires_in: int


@router.post("/telegram/link-code", response_model=TelegramLinkResponse)
async def telegram_link_code(current_user: User = Depends(get_current_active_user)):
    """Generate a one-time code and a t.me deep link that ties the user's
    private Telegram chat to their account (consumed by the bot poller)."""
    import secrets as pysecrets
    import redis.asyncio as aioredis
    from app.core.config import settings

    code = pysecrets.token_urlsafe(8)
    r = aioredis.from_url(settings.REDIS_URL)
    try:
        await r.set(f"investment_ai:tg_link:{code}", str(current_user.id), ex=600)
    finally:
        await r.aclose()
    return TelegramLinkResponse(
        link=f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={code}",
        expires_in=600,
    )


@router.get("/telegram/status")
async def telegram_status(current_user: User = Depends(get_current_active_user)):
    return {"linked": bool(current_user.telegram_chat_id)}


@router.delete("/telegram/link")
async def telegram_unlink(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.telegram_chat_id = None
    await db.flush()
    return {"linked": False}



# ─── Demo accounts for prospects ──────────────────────────────────────────────

DEMO_EMAIL_DOMAIN = "demo.investment-ai.app"


class DemoAccountRequest(BaseModel):
    label: Optional[str] = None


class DemoAccountResponse(BaseModel):
    email: str
    password: str
    label: str
    already_existed: bool


class DemoAccountRow(BaseModel):
    id: int
    email: str
    label: str
    is_active: bool
    created_at: datetime


def _demo_slug(label: Optional[str]) -> str:
    """A filesystem-safe, email-safe handle for the prospect.

    Hebrew company names are common here and would not survive an email local
    part, so anything outside [a-z0-9-] is dropped and a stable fallback is
    used when nothing usable remains.
    """
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", (label or "").strip().lower()).strip("-")[:24]
    return slug or "guest"



def _demo_password(length: int = 14) -> str:
    """A password that survives being read off a screen and typed on a phone.

    token_urlsafe produces hyphens and underscores, and the admin panel is a
    right-to-left page: a Latin string carrying punctuation gets reordered by
    the bidi algorithm, so the hyphen renders somewhere other than where it
    belongs and what the reader types is not what was generated. The alphabet
    below also drops the characters that look alike in most fonts — 0/O and
    1/l/I — since the recipient is usually retyping this by hand.
    """
    import secrets as pysecrets

    alphabet = ("ABCDEFGHJKLMNPQRSTUVWXYZ"
                "abcdefghijkmnopqrstuvwxyz"
                "23456789")
    while True:
        candidate = "".join(pysecrets.choice(alphabet) for _ in range(length))
        # Registration requires a digit; keep demo passwords to the same rule
        # so one can be reused to sign in anywhere the policy is enforced.
        if any(c.isdigit() for c in candidate) and any(c.isalpha() for c in candidate):
            return candidate


@router.post("/demo-account", response_model=DemoAccountResponse)
async def create_demo_account(
    request: DemoAccountRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Provision a read-only demo account for one prospect.

    One account per prospect, keyed by label. A single shared demo account
    cannot work: rotating its password to close out one evaluation locks out
    every other prospect still looking, and nothing anyone does can be told
    apart. Re-requesting the same label rotates only that account's password.

    The account is a plain client: not an admin, onboarded so it lands on the
    signals feed rather than the questionnaire, every notification channel off
    and no Telegram link so it never sends anything to the viewer, and both
    display preferences on so the feed is not silently filtered.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    from sqlalchemy import select as _select

    slug = _demo_slug(request.label)
    email = f"{slug}@{DEMO_EMAIL_DOMAIN}"
    password = _demo_password()

    existing = (await db.execute(_select(User).where(User.email == email))).scalar_one_or_none()
    user = existing or User(email=email, full_name=f"Demo — {request.label or slug}")

    user.hashed_password = get_password_hash(password)
    user.is_admin = False
    user.is_active = True
    user.is_onboarded = True
    user.preferred_language = "he"
    user.risk_profile = RiskProfile.HYBRID
    user.risk_score = 50.0
    user.investment_type = "BOTH"
    # Both on: with either off the feed is filtered and the viewer sees a
    # thinner product than the one being sold, with nothing to say why.
    user.allows_volatile = True
    user.allows_short = True
    user.allows_leveraged = False
    # Silence every outbound channel — a prospect evaluating the product must
    # not start receiving its alerts.
    user.notification_email = False
    user.notification_sms = False
    user.notification_push = False
    user.telegram_chat_id = None
    user.totp_enabled = False

    if existing is None:
        db.add(user)
    await db.flush()

    # Clear any brute-force lockout on this address. Failed attempts with the
    # old password lock the email for fifteen minutes, so without this a fresh
    # password still could not be used — and the rotation looks broken exactly
    # when someone is trying hardest to get in.
    await _login_fail_clear(email)

    logger.info("Demo account provisioned", email=email, reset=bool(existing))
    return DemoAccountResponse(
        email=email, password=password, label=request.label or slug,
        already_existed=bool(existing),
    )


@router.get("/demo-accounts", response_model=List[DemoAccountRow])
async def list_demo_accounts(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Every demo account handed out, so access can be reviewed and revoked."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    from sqlalchemy import select as _select

    rows = (await db.execute(
        _select(User).where(User.email.like(f"%@{DEMO_EMAIL_DOMAIN}")).order_by(User.id.desc())
    )).scalars().all()
    return [
        DemoAccountRow(
            id=u.id, email=u.email, is_active=u.is_active, created_at=u.created_at,
            label=u.full_name.replace("Demo — ", "") if u.full_name else u.email,
        )
        for u in rows
    ]


@router.post("/demo-accounts/{account_id}/revoke")
async def revoke_demo_account(
    account_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Close one prospect's access without touching anyone else's."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    from sqlalchemy import select as _select

    user = (await db.execute(_select(User).where(User.id == account_id))).scalar_one_or_none()
    if user is None or not user.email.endswith(f"@{DEMO_EMAIL_DOMAIN}"):
        raise HTTPException(status_code=404, detail="Not a demo account")
    user.is_active = False
    await db.flush()
    logger.info("Demo account revoked", email=user.email)
    return {"revoked": True, "email": user.email}
