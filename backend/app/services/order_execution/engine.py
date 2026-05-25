"""
Internal Broker / Order Execution Engine
Handles order placement, execution, portfolio updates, and cash management.
This is an internal engine - no external broker integration.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.core.config import settings
from app.db.models.order import Order, OrderType, OrderStatus
from app.db.models.portfolio import Portfolio
from app.db.models.user import User
from app.db.models.asset import Asset

logger = structlog.get_logger(__name__)


@dataclass
class ExposureCheck:
    allowed: bool
    warning: bool
    blocked: bool
    current_exposure_pct: float
    max_allowed_pct: float
    message: str


@dataclass
class OrderResult:
    success: bool
    order_id: Optional[int]
    message: str
    order: Optional[Order] = None


class OrderBook:
    """
    Simple in-memory order book for simulation.
    In production, this would interface with a real exchange.
    """

    def __init__(self):
        self._bids: Dict[str, List[Dict]] = {}  # symbol -> list of bid orders
        self._asks: Dict[str, List[Dict]] = {}  # symbol -> list of ask orders

    def get_best_bid(self, symbol: str) -> Optional[float]:
        bids = self._bids.get(symbol, [])
        if bids:
            return max(b["price"] for b in bids)
        return None

    def get_best_ask(self, symbol: str) -> Optional[float]:
        asks = self._asks.get(symbol, [])
        if asks:
            return min(a["price"] for a in asks)
        return None

    def get_mid_price(self, symbol: str, last_price: float) -> float:
        """Get mid price between bid and ask, fallback to last_price."""
        bid = self.get_best_bid(symbol)
        ask = self.get_best_ask(symbol)
        if bid and ask:
            return (bid + ask) / 2
        return last_price


class OrderExecutionEngine:
    """
    Internal broker engine for simulated order execution.
    Manages portfolio positions and cash balances.
    """

    def __init__(self):
        self.order_book = OrderBook()

    async def place_order(
        self,
        user_id: int,
        symbol: str,
        order_type: OrderType,
        quantity: float,
        price: float,
        recommendation_id: Optional[int] = None,
        notes: Optional[str] = None,
        db: AsyncSession = None,
    ) -> OrderResult:
        """
        Place an order. Validates funds/shares and creates order record.
        Returns OrderResult with success status.
        """
        try:
            # Fetch user
            user_result = await db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()
            if not user:
                return OrderResult(success=False, order_id=None, message="User not found")

            total_amount = quantity * price

            # Validate based on order type
            if order_type == OrderType.BUY:
                if not await self.validate_sufficient_funds(user_id, total_amount, db):
                    return OrderResult(
                        success=False,
                        order_id=None,
                        message=f"Insufficient funds. Required: ${total_amount:.2f}, Available: ${user.cash_balance:.2f}",
                    )
            elif order_type == OrderType.SELL:
                portfolio = await self._get_portfolio_position(user_id, symbol, db)
                if not portfolio or portfolio.quantity < quantity:
                    available = portfolio.quantity if portfolio else 0
                    return OrderResult(
                        success=False,
                        order_id=None,
                        message=f"Insufficient shares. Required: {quantity}, Available: {available:.4f}",
                    )

            # Fetch asset
            asset_result = await db.execute(select(Asset).where(Asset.symbol == symbol))
            asset = asset_result.scalar_one_or_none()
            asset_id = asset.id if asset else None

            # Create order
            order = Order(
                user_id=user_id,
                asset_id=asset_id,
                recommendation_id=recommendation_id,
                symbol=symbol,
                order_type=order_type,
                status=OrderStatus.PENDING,
                quantity=quantity,
                price_at_order=price,
                total_amount=total_amount,
                notes=notes,
            )
            db.add(order)
            await db.flush()

            logger.info(
                "Order placed",
                order_id=order.id,
                user_id=user_id,
                symbol=symbol,
                type=order_type,
                quantity=quantity,
                price=price,
            )

            return OrderResult(success=True, order_id=order.id, message="Order placed successfully", order=order)

        except Exception as e:
            logger.error("place_order failed", user_id=user_id, symbol=symbol, error=str(e))
            return OrderResult(success=False, order_id=None, message=f"Order failed: {str(e)}")

    async def execute_order(self, order_id: int, db: AsyncSession) -> OrderResult:
        """
        Execute a pending order. Updates portfolio position and cash balance.
        In simulation, we execute at the price_at_order (market order simulation).
        """
        try:
            order_result = await db.execute(select(Order).where(Order.id == order_id))
            order = order_result.scalar_one_or_none()

            if not order:
                return OrderResult(success=False, order_id=order_id, message="Order not found")

            if order.status != OrderStatus.PENDING:
                return OrderResult(
                    success=False,
                    order_id=order_id,
                    message=f"Order cannot be executed - status is {order.status}",
                )

            user_result = await db.execute(select(User).where(User.id == order.user_id))
            user = user_result.scalar_one_or_none()

            if not user:
                return OrderResult(success=False, order_id=order_id, message="User not found")

            # Apply small slippage for realism (0.05%)
            slippage_factor = 1.0005 if order.order_type == OrderType.BUY else 0.9995
            executed_price = order.price_at_order * slippage_factor
            executed_total = order.quantity * executed_price

            if order.order_type == OrderType.BUY:
                # Deduct cash
                if user.cash_balance < executed_total:
                    order.status = OrderStatus.REJECTED
                    order.rejection_reason = "Insufficient funds at execution time"
                    await db.flush()
                    return OrderResult(success=False, order_id=order_id, message="Insufficient funds")

                user.cash_balance -= executed_total

                # Update portfolio position
                await self._update_portfolio_buy(
                    user_id=order.user_id,
                    symbol=order.symbol,
                    asset_id=order.asset_id,
                    quantity=order.quantity,
                    price=executed_price,
                    db=db,
                )

            elif order.order_type == OrderType.SELL:
                portfolio = await self._get_portfolio_position(order.user_id, order.symbol, db)
                if not portfolio or portfolio.quantity < order.quantity:
                    order.status = OrderStatus.REJECTED
                    order.rejection_reason = "Insufficient shares at execution time"
                    await db.flush()
                    return OrderResult(success=False, order_id=order_id, message="Insufficient shares")

                # Add cash from sale
                user.cash_balance += executed_total

                # Update portfolio position
                await self._update_portfolio_sell(
                    portfolio=portfolio,
                    quantity=order.quantity,
                    db=db,
                )

            # Mark order as executed
            order.status = OrderStatus.EXECUTED
            order.executed_price = executed_price
            order.executed_total = executed_total
            order.executed_at = datetime.now(timezone.utc)

            await db.flush()

            logger.info(
                "Order executed",
                order_id=order_id,
                type=order.order_type,
                symbol=order.symbol,
                quantity=order.quantity,
                executed_price=executed_price,
                executed_total=executed_total,
            )

            return OrderResult(
                success=True,
                order_id=order_id,
                message=f"Order executed at ${executed_price:.2f}",
                order=order,
            )

        except Exception as e:
            logger.error("execute_order failed", order_id=order_id, error=str(e))
            return OrderResult(success=False, order_id=order_id, message=f"Execution failed: {str(e)}")

    async def cancel_order(self, order_id: int, user_id: int, db: AsyncSession) -> OrderResult:
        """Cancel a pending order."""
        try:
            result = await db.execute(
                select(Order).where(Order.id == order_id, Order.user_id == user_id)
            )
            order = result.scalar_one_or_none()

            if not order:
                return OrderResult(success=False, order_id=order_id, message="Order not found")

            if order.status != OrderStatus.PENDING:
                return OrderResult(
                    success=False,
                    order_id=order_id,
                    message=f"Cannot cancel order with status {order.status}",
                )

            order.status = OrderStatus.CANCELLED
            order.cancelled_at = datetime.now(timezone.utc)
            await db.flush()

            return OrderResult(success=True, order_id=order_id, message="Order cancelled successfully")

        except Exception as e:
            logger.error("cancel_order failed", order_id=order_id, error=str(e))
            return OrderResult(success=False, order_id=order_id, message=str(e))

    async def get_portfolio_summary(self, user_id: int, db: AsyncSession) -> Dict[str, Any]:
        """Get comprehensive portfolio summary with P&L for a user."""
        try:
            user_result = await db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()
            if not user:
                return {}

            portfolio_result = await db.execute(
                select(Portfolio).where(Portfolio.user_id == user_id, Portfolio.quantity > 0)
            )
            positions = portfolio_result.scalars().all()

            total_market_value = sum(p.current_value for p in positions if p.current_value)
            total_cost_basis = sum(p.quantity * p.avg_buy_price for p in positions)
            total_pnl = total_market_value - total_cost_basis
            total_pnl_pct = (total_pnl / total_cost_basis * 100) if total_cost_basis > 0 else 0.0
            total_value = total_market_value + user.cash_balance

            return {
                "user_id": user_id,
                "total_value": total_value,
                "cash_balance": user.cash_balance,
                "total_market_value": total_market_value,
                "total_cost_basis": total_cost_basis,
                "total_pnl": total_pnl,
                "total_pnl_pct": total_pnl_pct,
                "position_count": len(positions),
                "positions": [
                    {
                        "symbol": p.symbol,
                        "quantity": p.quantity,
                        "avg_buy_price": p.avg_buy_price,
                        "current_price": p.current_price,
                        "current_value": p.current_value,
                        "pnl": p.pnl,
                        "pnl_percentage": p.pnl_percentage,
                        "exposure_percentage": p.exposure_percentage,
                    }
                    for p in positions
                ],
                "summary_timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error("get_portfolio_summary failed", user_id=user_id, error=str(e))
            return {}

    async def validate_sufficient_funds(
        self, user_id: int, amount: float, db: AsyncSession
    ) -> bool:
        """Check if user has enough cash for a trade."""
        result = await db.execute(select(User.cash_balance).where(User.id == user_id))
        balance = result.scalar_one_or_none()
        return balance is not None and balance >= amount

    async def check_exposure(
        self,
        user_id: int,
        symbol: str,
        amount: float,
        db: AsyncSession,
    ) -> ExposureCheck:
        """Check if a trade would violate exposure limits."""
        summary = await self.get_portfolio_summary(user_id, db)
        total_value = summary.get("total_value", 0)

        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        max_pct = (user.max_single_asset_exposure if user else settings.MAX_SINGLE_ASSET_EXPOSURE) * 100

        if total_value <= 0:
            return ExposureCheck(
                allowed=True, warning=False, blocked=False,
                current_exposure_pct=0.0, max_allowed_pct=max_pct,
                message="No portfolio value to calculate exposure"
            )

        # Existing position value
        existing_value = 0.0
        for pos in summary.get("positions", []):
            if pos["symbol"] == symbol:
                existing_value = pos["current_value"]
                break

        new_total_exposure = existing_value + amount
        new_exposure_pct = (new_total_exposure / total_value) * 100

        if new_exposure_pct > max_pct * 1.5:
            return ExposureCheck(
                allowed=False, warning=False, blocked=True,
                current_exposure_pct=new_exposure_pct, max_allowed_pct=max_pct,
                message=f"Trade blocked: exposure would be {new_exposure_pct:.1f}% (max {max_pct:.1f}%)",
            )
        elif new_exposure_pct > max_pct:
            return ExposureCheck(
                allowed=True, warning=True, blocked=False,
                current_exposure_pct=new_exposure_pct, max_allowed_pct=max_pct,
                message=f"Warning: exposure would be {new_exposure_pct:.1f}% (recommended max {max_pct:.1f}%)",
            )
        else:
            return ExposureCheck(
                allowed=True, warning=False, blocked=False,
                current_exposure_pct=new_exposure_pct, max_allowed_pct=max_pct,
                message="Exposure within limits",
            )

    async def _get_portfolio_position(
        self, user_id: int, symbol: str, db: AsyncSession
    ) -> Optional[Portfolio]:
        result = await db.execute(
            select(Portfolio).where(Portfolio.user_id == user_id, Portfolio.symbol == symbol)
        )
        return result.scalar_one_or_none()

    async def _update_portfolio_buy(
        self,
        user_id: int,
        symbol: str,
        asset_id: Optional[int],
        quantity: float,
        price: float,
        db: AsyncSession,
    ) -> None:
        """Update or create portfolio position after a buy."""
        existing = await self._get_portfolio_position(user_id, symbol, db)

        if existing:
            # Calculate new average buy price
            total_quantity = existing.quantity + quantity
            new_avg_price = (
                (existing.quantity * existing.avg_buy_price + quantity * price) / total_quantity
            )
            existing.quantity = total_quantity
            existing.avg_buy_price = new_avg_price
            existing.current_price = price
            existing.current_value = total_quantity * price
            existing.pnl = existing.current_value - (total_quantity * new_avg_price)
            existing.pnl_percentage = ((price - new_avg_price) / new_avg_price * 100) if new_avg_price > 0 else 0.0
        else:
            portfolio = Portfolio(
                user_id=user_id,
                asset_id=asset_id,
                symbol=symbol,
                quantity=quantity,
                avg_buy_price=price,
                current_price=price,
                current_value=quantity * price,
                pnl=0.0,
                pnl_percentage=0.0,
                exposure_percentage=0.0,
            )
            db.add(portfolio)

        await db.flush()

    async def _update_portfolio_sell(
        self,
        portfolio: Portfolio,
        quantity: float,
        db: AsyncSession,
    ) -> None:
        """Update portfolio position after a sell."""
        portfolio.quantity -= quantity
        if portfolio.quantity <= 0.0001:
            portfolio.quantity = 0.0
            portfolio.current_value = 0.0
            portfolio.pnl = 0.0
            portfolio.pnl_percentage = 0.0
        else:
            portfolio.current_value = portfolio.quantity * portfolio.current_price
            portfolio.pnl = portfolio.current_value - (portfolio.quantity * portfolio.avg_buy_price)
            portfolio.pnl_percentage = (
                ((portfolio.current_price - portfolio.avg_buy_price) / portfolio.avg_buy_price * 100)
                if portfolio.avg_buy_price > 0 else 0.0
            )
        await db.flush()

    async def update_portfolio_prices(
        self, user_id: int, prices: Dict[str, float], db: AsyncSession
    ) -> None:
        """Update current prices and recalculate P&L for all positions."""
        portfolio_result = await db.execute(
            select(Portfolio).where(Portfolio.user_id == user_id, Portfolio.quantity > 0)
        )
        positions = portfolio_result.scalars().all()

        total_market_value = 0.0
        for pos in positions:
            if pos.symbol in prices:
                pos.current_price = prices[pos.symbol]
                pos.current_value = pos.quantity * pos.current_price
                pos.pnl = pos.current_value - (pos.quantity * pos.avg_buy_price)
                pos.pnl_percentage = (
                    ((pos.current_price - pos.avg_buy_price) / pos.avg_buy_price * 100)
                    if pos.avg_buy_price > 0 else 0.0
                )
            total_market_value += pos.current_value

        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        total_value = total_market_value + (user.cash_balance if user else 0)

        # Update exposure percentages
        for pos in positions:
            pos.exposure_percentage = (
                (pos.current_value / total_value * 100) if total_value > 0 else 0.0
            )

        await db.flush()


# Singleton
_engine: Optional[OrderExecutionEngine] = None


def get_order_execution_engine() -> OrderExecutionEngine:
    global _engine
    if _engine is None:
        _engine = OrderExecutionEngine()
    return _engine
