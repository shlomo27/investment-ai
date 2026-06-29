"""
Polygon.io Market Data Service
Free tier: previous-day OHLCV, ticker details (15-min delayed).
Used as 5th fallback in the market data chain.
"""
import asyncio
import httpx
from typing import Any, Dict, Optional
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

BASE_URL = "https://api.polygon.io"


class PolygonService:
    def __init__(self):
        self._api_key = settings.POLYGON_API_KEY

    def is_configured(self) -> bool:
        return bool(self._api_key and not self._api_key.startswith("your_"))

    async def get_prev_close(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get previous day close OHLCV — available on free tier."""
        if not self.is_configured():
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{BASE_URL}/v2/aggs/ticker/{symbol}/prev",
                    params={"adjusted": "true", "apiKey": self._api_key},
                )
                if resp.status_code != 200:
                    return None
                results = resp.json().get("results", [])
                if not results:
                    return None
                bar = results[0]
                price = float(bar.get("c", 0))
                if price == 0:
                    return None
                return {
                    "price": price,
                    "previous_close": price,
                    "volume": int(bar.get("v", 0)),
                    "open": float(bar.get("o", 0)),
                    "high": float(bar.get("h", 0)),
                    "low": float(bar.get("l", 0)),
                }
        except Exception as e:
            logger.debug("Polygon prev_close failed", symbol=symbol, error=str(e))
            return None

    async def get_ticker_details(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get company details — sector, market cap, description."""
        if not self.is_configured():
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{BASE_URL}/v3/reference/tickers/{symbol}",
                    params={"apiKey": self._api_key},
                )
                if resp.status_code != 200:
                    return None
                data = resp.json().get("results", {})
                mc = data.get("market_cap")
                return {
                    "sector": data.get("sic_description"),
                    "market_cap": float(mc) if mc else None,
                    "company_description": data.get("description", "")[:500],
                    "country": (data.get("locale") or "us").upper(),
                    "currency": (data.get("currency_name") or "usd").upper(),
                }
        except Exception as e:
            logger.debug("Polygon ticker_details failed", symbol=symbol, error=str(e))
            return None

    async def get_stock_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Combined previous-close price + ticker details."""
        if not self.is_configured():
            return None

        price_data, details = await asyncio.gather(
            self.get_prev_close(symbol),
            self.get_ticker_details(symbol),
            return_exceptions=True,
        )

        if isinstance(price_data, Exception) or not price_data or price_data.get("price", 0) == 0:
            return None

        result = {**price_data}
        if isinstance(details, dict) and details:
            for k, v in details.items():
                if v is not None:
                    result[k] = v

        return result


_polygon_service: Optional[PolygonService] = None


def get_polygon_service() -> PolygonService:
    global _polygon_service
    if _polygon_service is None:
        _polygon_service = PolygonService()
    return _polygon_service
