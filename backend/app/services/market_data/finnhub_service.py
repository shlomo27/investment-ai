"""
Finnhub Market Data + News Service
Free tier: 60 req/min, real-time US quotes, company news, basic financials.
Used as 4th fallback in market data chain; also enriches news pipeline.
"""
import asyncio
import httpx
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import structlog

from app.core.config import settings
from app.agents.state import NewsItem

logger = structlog.get_logger(__name__)

BASE_URL = "https://finnhub.io/api/v1"


class FinnhubService:
    def __init__(self):
        self._api_key = settings.FINNHUB_API_KEY

    def is_configured(self) -> bool:
        return bool(self._api_key and not self._api_key.startswith("your_"))

    def _headers(self) -> Dict[str, str]:
        return {"X-Finnhub-Token": self._api_key}

    async def get_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Real-time quote: current price, open, high, low, prev close."""
        if not self.is_configured():
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{BASE_URL}/quote",
                    params={"symbol": symbol},
                    headers=self._headers(),
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()
                price = float(data.get("c", 0))
                if price == 0:
                    return None
                return {
                    "price": price,
                    "previous_close": float(data.get("pc", 0)),
                    "open": float(data.get("o", 0)),
                    "high": float(data.get("h", 0)),
                    "low": float(data.get("l", 0)),
                }
        except Exception as e:
            logger.debug("Finnhub quote failed", symbol=symbol, error=str(e))
            return None

    async def get_profile(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Company profile: sector, market cap, country, exchange."""
        if not self.is_configured():
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{BASE_URL}/stock/profile2",
                    params={"symbol": symbol},
                    headers=self._headers(),
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()
                if not data.get("name"):
                    return None
                mc = data.get("marketCapitalization")
                return {
                    "sector": data.get("finnhubIndustry"),
                    "country": data.get("country", "US"),
                    "currency": data.get("currency", "USD"),
                    "market_cap": float(mc) * 1_000_000 if mc else None,
                    "exchange": data.get("exchange"),
                }
        except Exception as e:
            logger.debug("Finnhub profile failed", symbol=symbol, error=str(e))
            return None

    async def get_basic_financials(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Basic financial metrics: PE, beta, 52w high/low, margins."""
        if not self.is_configured():
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{BASE_URL}/stock/metric",
                    params={"symbol": symbol, "metric": "all"},
                    headers=self._headers(),
                )
                if resp.status_code != 200:
                    return None
                m = resp.json().get("metric", {})
                return {
                    "pe_ratio": m.get("peBasicExclExtraTTM"),
                    "price_to_book": m.get("pbQuarterly"),
                    "price_to_sales": m.get("psTTM"),
                    "revenue_growth": m.get("revenueGrowthTTMYoy"),
                    "profit_margin": m.get("netProfitMarginTTM"),
                    "roe": m.get("roeTTM"),
                    "roa": m.get("roaTTM"),
                    "beta": m.get("beta"),
                    "fifty_two_week_high": m.get("52WeekHigh"),
                    "fifty_two_week_low": m.get("52WeekLow"),
                    "dividend_yield": m.get("dividendYieldIndicatedAnnual"),
                    "debt_to_equity": m.get("totalDebt/totalEquityAnnual"),
                    "current_ratio": m.get("currentRatioAnnual"),
                }
        except Exception as e:
            logger.debug("Finnhub financials failed", symbol=symbol, error=str(e))
            return None

    async def get_stock_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Full stock info: quote + profile + financials combined."""
        if not self.is_configured():
            return None

        quote, profile, financials = await asyncio.gather(
            self.get_quote(symbol),
            self.get_profile(symbol),
            self.get_basic_financials(symbol),
            return_exceptions=True,
        )

        if isinstance(quote, Exception) or not quote or quote.get("price", 0) == 0:
            return None

        result = {**quote}
        if isinstance(profile, dict) and profile:
            for k, v in profile.items():
                if v is not None:
                    result[k] = v
        if isinstance(financials, dict) and financials:
            for k, v in financials.items():
                if k not in result and v is not None:
                    result[k] = v

        return result

    async def get_news(self, symbol: str, days_back: int = 7) -> List[NewsItem]:
        """Company news from Finnhub — supplements NewsAPI."""
        if not self.is_configured():
            return []
        try:
            from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
            to_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{BASE_URL}/company-news",
                    params={"symbol": symbol, "from": from_date, "to": to_date},
                    headers=self._headers(),
                )
                if resp.status_code != 200:
                    return []

                articles = resp.json()
                items: List[NewsItem] = []
                for a in articles[:20]:
                    headline = (a.get("headline") or "").strip()
                    if not headline:
                        continue
                    ts = a.get("datetime", 0)
                    pub_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else ""
                    items.append(NewsItem(
                        title=headline[:300],
                        source=a.get("source", "Finnhub"),
                        url=a.get("url", ""),
                        published_at=pub_at,
                        summary=(a.get("summary") or "")[:600],
                        sentiment=0.0,
                    ))
                return items
        except Exception as e:
            logger.debug("Finnhub news failed", symbol=symbol, error=str(e))
            return []


_finnhub_service: Optional[FinnhubService] = None


def get_finnhub_service() -> FinnhubService:
    global _finnhub_service
    if _finnhub_service is None:
        _finnhub_service = FinnhubService()
    return _finnhub_service
