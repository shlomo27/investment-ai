"""
Performance Tracking Service
Automatically tracks recommendation outcomes by comparing entry price to
current price after 30, 60, and 90-day intervals.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.db.models.recommendation import Recommendation, RecommendationStatus, RecommendationType

logger = structlog.get_logger(__name__)

OUTCOME_CHECK_DAYS = 30  # Check outcome after 30 days
WIN_THRESHOLD_PCT = 5.0  # +5% = WIN
LOSS_THRESHOLD_PCT = -5.0  # -5% = LOSS
SPY_ANNUAL_RETURN = 0.10  # S&P 500 benchmark (10% annualized)


class PerformanceService:

    async def track_pending_outcomes(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Scan all approved recommendations older than 30 days that haven't been
        outcome-tracked yet, fetch current prices, and record results.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=OUTCOME_CHECK_DAYS)

        result = await db.execute(
            select(Recommendation).where(
                and_(
                    Recommendation.status == RecommendationStatus.APPROVED,
                    Recommendation.approved_at <= cutoff,
                    Recommendation.outcome_tracked_at.is_(None),
                    Recommendation.current_price_at_recommendation.isnot(None),
                )
            )
        )
        recs = result.scalars().all()

        tracked = 0
        errors = 0

        for rec in recs:
            try:
                current_price = await self._fetch_current_price(rec.symbol)
                if current_price is None or current_price <= 0:
                    continue

                entry_price = rec.current_price_at_recommendation
                if not entry_price or entry_price <= 0:
                    continue

                return_pct = (current_price - entry_price) / entry_price * 100

                # Expected market return over the holding period (annualized SPY)
                days_held = (datetime.now(timezone.utc) - rec.approved_at).days
                market_return_pct = (SPY_ANNUAL_RETURN / 365) * days_held * 100

                vs_market = return_pct - market_return_pct

                # Determine result considering recommendation direction
                rec_type = rec.recommendation_type
                is_buy = rec_type in (RecommendationType.BUY, RecommendationType.STRONG_BUY)
                is_sell = rec_type in (RecommendationType.SELL, RecommendationType.STRONG_SELL)

                if is_buy:
                    if return_pct >= WIN_THRESHOLD_PCT:
                        outcome = "WIN"
                    elif return_pct <= LOSS_THRESHOLD_PCT:
                        outcome = "LOSS"
                    else:
                        outcome = "NEUTRAL"
                elif is_sell:
                    # For SELL: stock going down is a WIN
                    if return_pct <= LOSS_THRESHOLD_PCT:
                        outcome = "WIN"
                    elif return_pct >= WIN_THRESHOLD_PCT:
                        outcome = "LOSS"
                    else:
                        outcome = "NEUTRAL"
                else:
                    outcome = "NEUTRAL"

                rec.outcome_price = round(current_price, 4)
                rec.outcome_return_pct = round(return_pct, 2)
                rec.outcome_vs_market_pct = round(vs_market, 2)
                rec.outcome_date = datetime.now(timezone.utc)
                rec.outcome_tracked_at = datetime.now(timezone.utc)
                rec.outcome_result = outcome
                tracked += 1

            except Exception as e:
                logger.warning("Failed to track outcome", rec_id=rec.id, symbol=rec.symbol, error=str(e))
                errors += 1

        await db.flush()
        logger.info("Outcome tracking complete", tracked=tracked, errors=errors)
        return {"tracked": tracked, "errors": errors}

    async def get_performance_summary(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Returns overall recommendation performance statistics.
        """
        result = await db.execute(
            select(Recommendation).where(
                Recommendation.outcome_result.isnot(None)
            )
        )
        tracked = result.scalars().all()

        if not tracked:
            return {
                "total_tracked": 0,
                "win_count": 0,
                "loss_count": 0,
                "neutral_count": 0,
                "win_rate_pct": 0.0,
                "avg_return_pct": 0.0,
                "avg_vs_market_pct": 0.0,
                "best_trade": None,
                "worst_trade": None,
                "recent_outcomes": [],
            }

        wins = [r for r in tracked if r.outcome_result == "WIN"]
        losses = [r for r in tracked if r.outcome_result == "LOSS"]
        neutrals = [r for r in tracked if r.outcome_result == "NEUTRAL"]

        returns = [r.outcome_return_pct for r in tracked if r.outcome_return_pct is not None]
        vs_market = [r.outcome_vs_market_pct for r in tracked if r.outcome_vs_market_pct is not None]

        best = max(tracked, key=lambda r: r.outcome_return_pct or -999)
        worst = min(tracked, key=lambda r: r.outcome_return_pct or 999)

        recent = sorted(tracked, key=lambda r: r.outcome_date or datetime.min, reverse=True)[:10]

        return {
            "total_tracked": len(tracked),
            "win_count": len(wins),
            "loss_count": len(losses),
            "neutral_count": len(neutrals),
            "win_rate_pct": round(len(wins) / len(tracked) * 100, 1),
            "avg_return_pct": round(sum(returns) / len(returns), 2) if returns else 0.0,
            "avg_vs_market_pct": round(sum(vs_market) / len(vs_market), 2) if vs_market else 0.0,
            "best_trade": {
                "symbol": best.symbol,
                "return_pct": best.outcome_return_pct,
                "type": best.recommendation_type.value,
                "date": best.approved_at.isoformat() if best.approved_at else None,
            } if best else None,
            "worst_trade": {
                "symbol": worst.symbol,
                "return_pct": worst.outcome_return_pct,
                "type": worst.recommendation_type.value,
                "date": worst.approved_at.isoformat() if worst.approved_at else None,
            } if worst else None,
            "recent_outcomes": [
                {
                    "id": r.id,
                    "symbol": r.symbol,
                    "type": r.recommendation_type.value,
                    "entry_price": r.current_price_at_recommendation,
                    "outcome_price": r.outcome_price,
                    "return_pct": r.outcome_return_pct,
                    "vs_market_pct": r.outcome_vs_market_pct,
                    "result": r.outcome_result,
                    "date": r.approved_at.isoformat() if r.approved_at else None,
                }
                for r in recent
            ],
        }

    async def get_comparison_chart(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Build AI vs S&P 500 comparison chart.
        Groups tracked recommendations by month, computes cumulative returns
        for both the AI portfolio and a buy-and-hold SPY strategy.
        """
        from collections import defaultdict

        result = await db.execute(
            select(Recommendation).where(
                and_(
                    Recommendation.outcome_result.isnot(None),
                    Recommendation.outcome_result != "PENDING",
                    Recommendation.outcome_return_pct.isnot(None),
                    Recommendation.approved_at.isnot(None),
                )
            ).order_by(Recommendation.approved_at)
        )
        recs = result.scalars().all()

        if not recs:
            return {
                "data_points": [],
                "total_ai_return": 0.0,
                "total_spy_return": 0.0,
                "alpha": 0.0,
                "using_real_spy": False,
            }

        # Group by month
        monthly: Dict[str, list] = defaultdict(list)
        for rec in recs:
            month_key = rec.approved_at.strftime("%Y-%m")
            ai_return = rec.outcome_return_pct or 0.0
            spy_est = ai_return - (rec.outcome_vs_market_pct or 0.0)
            monthly[month_key].append({"ai": ai_return, "spy_est": spy_est})

        # Fetch real SPY monthly returns
        spy_real = await self._fetch_spy_monthly_returns(
            start=recs[0].approved_at.date(),
            end=recs[-1].approved_at.date(),
        )

        ai_cum = 100.0
        spy_cum = 100.0
        data_points = []

        for month in sorted(monthly.keys()):
            trades = monthly[month]
            avg_ai = sum(t["ai"] for t in trades) / len(trades)
            real_spy = spy_real.get(month)
            avg_spy = real_spy if real_spy is not None else (
                sum(t["spy_est"] for t in trades) / len(trades)
            )

            ai_cum *= (1 + avg_ai / 100)
            spy_cum *= (1 + avg_spy / 100)

            data_points.append({
                "month": month,
                "ai_value": round(ai_cum, 2),
                "spy_value": round(spy_cum, 2),
                "ai_month_return": round(avg_ai, 2),
                "spy_month_return": round(avg_spy, 2),
                "trade_count": len(trades),
            })

        total_ai = round(ai_cum - 100, 2)
        total_spy = round(spy_cum - 100, 2)

        return {
            "data_points": data_points,
            "total_ai_return": total_ai,
            "total_spy_return": total_spy,
            "alpha": round(total_ai - total_spy, 2),
            "start_value": 100,
            "end_ai_value": round(ai_cum, 2),
            "end_spy_value": round(spy_cum, 2),
            "using_real_spy": bool(spy_real),
        }

    async def _fetch_spy_monthly_returns(self, start, end) -> Dict[str, float]:
        """Fetch real SPY monthly returns from Yahoo Finance."""
        try:
            import yfinance as yf
            from datetime import date, timedelta

            fetch_start = start.replace(day=1)
            fetch_end = end + timedelta(days=35)

            ticker = yf.Ticker("SPY")
            hist = ticker.history(
                start=fetch_start.isoformat(),
                end=fetch_end.isoformat(),
                interval="1mo",
            )
            monthly: Dict[str, float] = {}
            for idx, row in hist.iterrows():
                if row.get("Open", 0) > 0:
                    monthly[idx.strftime("%Y-%m")] = round(
                        ((row["Close"] - row["Open"]) / row["Open"]) * 100, 2
                    )
            return monthly
        except Exception as e:
            logger.warning("SPY monthly fetch failed", error=str(e))
            return {}

    async def get_performance_timeline(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """Monthly aggregated win rate, avg return, vs market — for the timeline bar chart."""
        from collections import defaultdict

        result = await db.execute(
            select(Recommendation).where(
                and_(
                    Recommendation.outcome_result.isnot(None),
                    Recommendation.outcome_result != "PENDING",
                    Recommendation.approved_at.isnot(None),
                )
            ).order_by(Recommendation.approved_at)
        )
        recs = result.scalars().all()

        monthly: Dict[str, Any] = defaultdict(lambda: {
            "wins": 0, "losses": 0, "neutral": 0,
            "returns": [], "vs_market": [],
        })

        for rec in recs:
            m = monthly[rec.approved_at.strftime("%Y-%m")]
            if rec.outcome_result == "WIN":
                m["wins"] += 1
            elif rec.outcome_result == "LOSS":
                m["losses"] += 1
            else:
                m["neutral"] += 1
            if rec.outcome_return_pct is not None:
                m["returns"].append(rec.outcome_return_pct)
            if rec.outcome_vs_market_pct is not None:
                m["vs_market"].append(rec.outcome_vs_market_pct)

        timeline = []
        for month in sorted(monthly.keys()):
            m = monthly[month]
            total = m["wins"] + m["losses"] + m["neutral"]
            win_rate = round(m["wins"] / total * 100, 1) if total else 0.0
            avg_ret = round(sum(m["returns"]) / len(m["returns"]), 2) if m["returns"] else 0.0
            avg_vs = round(sum(m["vs_market"]) / len(m["vs_market"]), 2) if m["vs_market"] else 0.0
            timeline.append({
                "month": month,
                "win_rate": win_rate,
                "avg_return": avg_ret,
                "avg_vs_market": avg_vs,
                "total": total,
                "wins": m["wins"],
                "losses": m["losses"],
                "neutral": m["neutral"],
            })

        return timeline

    async def take_portfolio_snapshot(self, db: AsyncSession) -> Dict[str, Any]:
        """Take a daily snapshot of every active user's portfolio value."""
        from app.db.models.user import User
        from app.db.models.portfolio import Portfolio
        from app.db.models.portfolio_history import PortfolioHistory
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from datetime import date

        now = datetime.now(timezone.utc)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        users_result = await db.execute(select(User).where(User.is_active == True))
        users = users_result.scalars().all()

        snapped = 0
        for user in users:
            port_result = await db.execute(
                select(Portfolio).where(Portfolio.user_id == user.id)
            )
            positions = port_result.scalars().all()

            market_value = sum(p.current_value or 0 for p in positions)
            total_value = market_value + user.cash_balance
            total_pnl = sum(p.pnl or 0 for p in positions)
            total_pnl_pct = (total_pnl / (total_value - total_pnl) * 100) if (total_value - total_pnl) > 0 else 0.0

            stmt = pg_insert(PortfolioHistory).values(
                user_id=user.id,
                snapshot_date=today,
                total_value=round(total_value, 2),
                cash_balance=round(user.cash_balance, 2),
                market_value=round(market_value, 2),
                total_pnl=round(total_pnl, 2),
                total_pnl_pct=round(total_pnl_pct, 2),
            ).on_conflict_do_update(
                constraint="uq_portfolio_history_user_date",
                set_={
                    "total_value": round(total_value, 2),
                    "cash_balance": round(user.cash_balance, 2),
                    "market_value": round(market_value, 2),
                    "total_pnl": round(total_pnl, 2),
                    "total_pnl_pct": round(total_pnl_pct, 2),
                }
            )
            await db.execute(stmt)
            snapped += 1

        await db.flush()
        logger.info("Portfolio snapshot taken", users=snapped, date=today.isoformat())
        return {"snapped": snapped, "date": today.isoformat()}

    async def run_backtest(
        self, db: AsyncSession, initial_capital: float = 100000.0
    ) -> Dict[str, Any]:
        """
        Simulate equal-weight portfolio using all tracked recommendations.
        Each recommendation receives initial_capital / n_trades allocation.
        Returns equity curve + risk metrics (max drawdown, Sharpe ratio).
        """
        import math
        from collections import defaultdict

        result = await db.execute(
            select(Recommendation).where(
                and_(
                    Recommendation.outcome_result.isnot(None),
                    Recommendation.outcome_return_pct.isnot(None),
                    Recommendation.current_price_at_recommendation.isnot(None),
                    Recommendation.approved_at.isnot(None),
                    Recommendation.outcome_date.isnot(None),
                )
            ).order_by(Recommendation.approved_at)
        )
        recs = result.scalars().all()

        if len(recs) < 2:
            return {
                "data_points": [],
                "initial_capital": initial_capital,
                "final_value": initial_capital,
                "total_return_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "sharpe_ratio": 0.0,
                "win_rate_pct": 0.0,
                "total_trades": len(recs),
                "message": "At least 2 completed recommendations required for backtesting",
            }

        n_trades = len(recs)
        position_size = initial_capital / n_trades

        # Build chronological entry/exit events
        events: list = []
        for rec in recs:
            events.append({
                "date": rec.approved_at.date(),
                "type": "entry",
                "amount": position_size,
            })
            pnl = position_size * (rec.outcome_return_pct / 100)
            events.append({
                "date": rec.outcome_date.date(),
                "type": "exit",
                "amount": position_size,
                "pnl": pnl,
            })
        events.sort(key=lambda e: (e["date"], 0 if e["type"] == "exit" else 1))

        # Simulate portfolio through events
        cash = initial_capital
        invested = 0.0
        peak = initial_capital
        max_drawdown = 0.0
        monthly_snapshots: dict = {}

        for ev in events:
            if ev["type"] == "entry":
                cash -= ev["amount"]
                invested += ev["amount"]
            else:
                cash += ev["amount"] + ev["pnl"]
                invested -= ev["amount"]

            portfolio_value = cash + invested
            if portfolio_value > peak:
                peak = portfolio_value
            drawdown = (peak - portfolio_value) / peak * 100 if peak > 0 else 0.0
            if drawdown > max_drawdown:
                max_drawdown = drawdown

            month_key = ev["date"].strftime("%Y-%m")
            monthly_snapshots[month_key] = round(portfolio_value, 2)

        # Build monthly data points
        data_points = []
        monthly_returns_list: list = []
        prev_val = initial_capital
        for month in sorted(monthly_snapshots.keys()):
            val = monthly_snapshots[month]
            month_ret = (val - prev_val) / prev_val * 100 if prev_val > 0 else 0.0
            monthly_returns_list.append(month_ret)
            data_points.append({
                "month": month,
                "value": val,
                "return_pct": round(month_ret, 2),
            })
            prev_val = val

        final_value = data_points[-1]["value"] if data_points else initial_capital
        total_return = (final_value - initial_capital) / initial_capital * 100

        # Annualized Sharpe (risk-free ≈ 0 for simplicity)
        sharpe = 0.0
        if len(monthly_returns_list) > 1:
            avg = sum(monthly_returns_list) / len(monthly_returns_list)
            variance = sum((r - avg) ** 2 for r in monthly_returns_list) / (len(monthly_returns_list) - 1)
            std = math.sqrt(variance) if variance > 0 else 0.0
            if std > 0:
                sharpe = round((avg / std) * (12 ** 0.5), 2)

        wins = sum(1 for r in recs if r.outcome_result == "WIN")

        return {
            "initial_capital": initial_capital,
            "final_value": round(final_value, 2),
            "total_return_pct": round(total_return, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "sharpe_ratio": sharpe,
            "win_rate_pct": round(wins / n_trades * 100, 1),
            "total_trades": n_trades,
            "data_points": data_points,
        }

    async def check_price_alerts(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """
        Check watchlist items for price alert triggers and send notifications.
        Returns list of triggered alerts.
        """
        from app.db.models.watchlist import Watchlist
        from sqlalchemy import or_

        result = await db.execute(
            select(Watchlist).where(
                or_(
                    Watchlist.alert_price_above.isnot(None),
                    Watchlist.alert_price_below.isnot(None),
                )
            )
        )
        items = result.scalars().all()

        triggered = []
        for item in items:
            try:
                current_price = await self._fetch_current_price(item.symbol)
                if current_price is None or current_price <= 0:
                    continue

                alert_fired = False
                direction = None

                if item.alert_price_above and current_price >= item.alert_price_above:
                    alert_fired = True
                    direction = "ABOVE"
                elif item.alert_price_below and current_price <= item.alert_price_below:
                    alert_fired = True
                    direction = "BELOW"

                if alert_fired:
                    item.alert_triggered_at = datetime.now(timezone.utc)
                    # Clear the alert so it doesn't re-fire
                    if direction == "ABOVE":
                        item.alert_price_above = None
                    else:
                        item.alert_price_below = None

                    triggered.append({
                        "symbol": item.symbol,
                        "user_id": item.user_id,
                        "current_price": current_price,
                        "direction": direction,
                        "watchlist_id": item.id,
                    })
            except Exception as e:
                logger.warning("Price alert check failed", symbol=item.symbol, error=str(e))

        await db.flush()
        return triggered

    @staticmethod
    async def _fetch_current_price(symbol: str) -> Optional[float]:
        """Fetch current price using the data fallback chain."""
        try:
            from app.services.market_data.yahoo_service import YahooFinanceService
            result = await YahooFinanceService().get_stock_info(symbol)
            if result and result.get("price", 0) > 0:
                return float(result["price"])
        except Exception:
            pass

        try:
            from app.services.market_data.finnhub_service import get_finnhub_service
            quote = await get_finnhub_service().get_quote(symbol)
            if quote and quote.get("c", 0) > 0:
                return float(quote["c"])
        except Exception:
            pass

        return None


_performance_service: Optional[PerformanceService] = None


def get_performance_service() -> PerformanceService:
    global _performance_service
    if _performance_service is None:
        _performance_service = PerformanceService()
    return _performance_service
