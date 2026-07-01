"""
Earnings Calendar Service
Uses Finnhub to fetch upcoming earnings dates for watchlist symbols.
Sends proactive notifications when earnings are within 3 days.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import structlog
import httpx

from app.core.config import settings

logger = structlog.get_logger(__name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"


class EarningsCalendarService:
    def __init__(self):
        self._timeout = httpx.Timeout(15.0)
        self._enabled = bool(settings.FINNHUB_API_KEY)

    async def get_upcoming_earnings(
        self, symbols: List[str], days_ahead: int = 14
    ) -> List[Dict[str, Any]]:
        """
        Returns upcoming earnings dates for the given symbols within the next N days.
        """
        if not self._enabled:
            return []

        from_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        to_date = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{FINNHUB_BASE}/calendar/earnings",
                    params={
                        "from": from_date,
                        "to": to_date,
                        "token": settings.FINNHUB_API_KEY,
                    },
                )
                if resp.status_code != 200:
                    return []

                data = resp.json()
                earnings_list = data.get("earningsCalendar", [])

                symbols_upper = {s.upper() for s in symbols}
                results = []
                for item in earnings_list:
                    symbol = (item.get("symbol") or "").upper()
                    if not symbols_upper or symbol in symbols_upper:
                        earnings_date = item.get("date", "")
                        days_until = self._days_until(earnings_date)
                        results.append({
                            "symbol": symbol,
                            "earnings_date": earnings_date,
                            "eps_estimate": item.get("epsEstimate"),
                            "eps_actual": item.get("epsActual"),
                            "revenue_estimate": item.get("revenueEstimate"),
                            "revenue_actual": item.get("revenueActual"),
                            "quarter": item.get("quarter"),
                            "year": item.get("year"),
                            "days_until": days_until,
                            "is_imminent": days_until is not None and 0 <= days_until <= 3,
                        })

                results.sort(key=lambda x: x.get("earnings_date", ""))
                return results

        except Exception as e:
            logger.debug("Earnings calendar fetch failed", error=str(e))
            return []

    async def get_earnings_for_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get next upcoming earnings date for a single symbol."""
        results = await self.get_upcoming_earnings([symbol], days_ahead=90)
        future = [r for r in results if r.get("days_until") is not None and r["days_until"] >= 0]
        return future[0] if future else None

    @staticmethod
    def _days_until(date_str: str) -> Optional[int]:
        try:
            target = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            return (target - now).days
        except Exception:
            return None

    async def check_imminent_earnings_and_notify(
        self,
        symbols: List[str],
        user_id: int,
        db: Any,
    ) -> List[str]:
        """
        Check if any watchlist symbols have earnings within 3 days.
        Sends notifications for each. Returns list of symbols notified.
        """
        upcoming = await self.get_upcoming_earnings(symbols, days_ahead=3)
        imminent = [e for e in upcoming if e.get("is_imminent")]

        notified = []
        for event in imminent:
            symbol = event["symbol"]
            days = event["days_until"]
            date_str = event["earnings_date"]
            eps_est = event.get("eps_estimate")

            try:
                from app.services.notifications.service import get_notification_service
                from app.db.models.notification import NotificationType

                msg_he = f"⚠️ {symbol} מדווחת על רווחים בעוד {days} ימים ({date_str})"
                msg_en = f"⚠️ {symbol} reports earnings in {days} day(s) ({date_str})"
                if eps_est:
                    msg_he += f" | תחזית EPS: ${eps_est:.2f}"
                    msg_en += f" | EPS estimate: ${eps_est:.2f}"

                await get_notification_service().send_notification(
                    user_id=user_id,
                    recommendation_id=None,
                    internal_detail={
                        "type": "EARNINGS_CALENDAR",
                        "symbol": symbol,
                        "earnings_date": date_str,
                        "days_until": days,
                        "eps_estimate": eps_est,
                        "message_he": msg_he,
                        "message_en": msg_en,
                    },
                    db=db,
                    notification_type=NotificationType.SYSTEM,
                    title=f"דיווח רווחים קרוב — {symbol}" if True else f"Upcoming Earnings — {symbol}",
                )
                notified.append(symbol)
            except Exception as e:
                logger.warning("Failed to send earnings notification", symbol=symbol, error=str(e))

        return notified


_earnings_service: Optional[EarningsCalendarService] = None


def get_earnings_calendar_service() -> EarningsCalendarService:
    global _earnings_service
    if _earnings_service is None:
        _earnings_service = EarningsCalendarService()
    return _earnings_service
