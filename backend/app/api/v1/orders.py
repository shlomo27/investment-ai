"""
Orders API routes
POST /orders, GET /orders, GET /orders/{id}, DELETE /orders/{id}, POST /orders/{id}/confirm
"""
from datetime import datetime
from typing import List, Optional
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.database import get_db
from app.core.security import get_current_active_user
from app.db.models.user import User
from app.db.models.order import Order, OrderType, OrderStatus
from app.db.models.asset import Asset
from app.services.order_execution.engine import get_order_execution_engine
from app.services.risk.manager import get_risk_manager

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/orders", tags=["Orders"])


class CreateOrderRequest(BaseModel):
    symbol: str
    order_type: OrderType
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    recommendation_id: Optional[int] = None
    notes: Optional[str] = None


class OrderResponse(BaseModel):
    id: int
    symbol: str
    order_type: OrderType
    status: OrderStatus
    quantity: float
    price_at_order: float
    executed_price: Optional[float]
    total_amount: float
    executed_total: Optional[float]
    notes: Optional[str]
    rejection_reason: Optional[str]
    created_at: datetime
    executed_at: Optional[datetime]
    cancelled_at: Optional[datetime]

    class Config:
        from_attributes = True


class ExposureCheckResponse(BaseModel):
    allowed: bool
    warning: bool
    blocked: bool
    current_exposure_pct: float
    max_allowed_pct: float
    message: str


@router.post("/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    request: CreateOrderRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new order (BUY or SELL).
    Validates funds, exposure limits, and executes immediately in simulation mode.
    """
    if not current_user.is_onboarded:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please complete onboarding before trading",
        )

    engine = get_order_execution_engine()
    risk_manager = get_risk_manager()

    symbol = request.symbol.upper()
    total_amount = request.quantity * request.price

    # Check exposure limits for BUY orders
    if request.order_type == OrderType.BUY:
        exposure_check = await risk_manager.check_exposure(
            current_user.id, symbol, total_amount, db
        )
        if exposure_check.get("blocked"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=exposure_check.get("message"),
            )

    # Place order
    result = await engine.place_order(
        user_id=current_user.id,
        symbol=symbol,
        order_type=request.order_type,
        quantity=request.quantity,
        price=request.price,
        recommendation_id=request.recommendation_id,
        notes=request.notes,
        db=db,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message,
        )

    # Auto-execute in simulation mode
    exec_result = await engine.execute_order(result.order_id, db)

    if not exec_result.success:
        logger.warning("Order execution failed after placement", order_id=result.order_id)

    # Fetch final order state
    order_result = await db.execute(select(Order).where(Order.id == result.order_id))
    order = order_result.scalar_one()

    return OrderResponse.from_orm(order)


@router.get("/", response_model=List[OrderResponse])
async def get_orders(
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get order history for the current user."""
    query = select(Order).where(Order.user_id == current_user.id)

    if status_filter:
        try:
            status_enum = OrderStatus(status_filter.upper())
            query = query.where(Order.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}",
            )

    query = query.order_by(desc(Order.created_at)).offset(offset).limit(limit)
    result = await db.execute(query)
    orders = result.scalars().all()

    return [OrderResponse.from_orm(o) for o in orders]


@router.get("/exposure-check")
async def check_exposure(
    symbol: str,
    amount: float,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Check if a trade would violate exposure limits before placing."""
    risk_manager = get_risk_manager()
    return await risk_manager.check_exposure(
        current_user.id,
        symbol.upper(),
        amount,
        db,
    )


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific order by ID."""
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.user_id == current_user.id)
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    return OrderResponse.from_orm(order)


@router.delete("/{order_id}")
async def cancel_order(
    order_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a pending order."""
    engine = get_order_execution_engine()
    result = await engine.cancel_order(order_id, current_user.id, db)

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message,
        )

    return {"message": result.message, "order_id": order_id}


@router.post("/{order_id}/confirm")
async def confirm_order(
    order_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually confirm/execute a pending order (if auto-execute is disabled)."""
    engine = get_order_execution_engine()

    # Verify ownership
    order_result = await db.execute(
        select(Order).where(Order.id == order_id, Order.user_id == current_user.id)
    )
    order = order_result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order.status != OrderStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order is {order.status} - cannot confirm",
        )

    result = await engine.execute_order(order_id, db)

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message,
        )

    order_result2 = await db.execute(select(Order).where(Order.id == order_id))
    final_order = order_result2.scalar_one()

    return OrderResponse.from_orm(final_order)
