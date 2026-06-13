"""
Authentication API routes
POST /register, POST /login, POST /logout, GET /me, PUT /profile
"""
from datetime import datetime, timezone
from typing import Optional
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
    preferred_language: str
    notification_email: bool
    notification_sms: bool
    notification_push: bool
    created_at: datetime

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


@router.post("/login", response_model=AuthResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Login with email and password."""
    result = await db.execute(select(User).where(User.email == request.email.lower()))
    user = result.scalar_one_or_none()

    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

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
    refresh_token: str,
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token using refresh token."""
    token_data = verify_token(refresh_token, token_type="refresh")

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
