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
                so = data.get("shareOutstanding")
                return {
                    "sector": data.get("finnhubIndustry"),
                    "country": data.get("country", "US"),
                    "currency": data.get("currency", "USD"),
                    "market_cap": float(mc) * 1_000_000 if mc else None,
                    "share_outstanding": float(so) * 1_000_000 if so else None,
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

                def _first(*keys):
                    """Finnhub reports the same metric under different names
                    depending on plan/stock — take the first that exists."""
                    for k in keys:
                        v = m.get(k)
                        if v is not None:
                            return v
                    return None

                return {
                    "pe_ratio": _first("peBasicExclExtraTTM", "peTTM", "peExclExtraTTM",
                                       "peInclExtraTTM", "peNormalizedAnnual", "peAnnual"),
                    "price_to_book": _first("pbQuarterly", "pbAnnual", "ptbvQuarterly"),
                    "price_to_sales": _first("psTTM", "psAnnual"),
                    "revenue_growth": _first("revenueGrowthTTMYoy", "revenueGrowthQuarterlyYoy"),
                    "profit_margin": _first("netProfitMarginTTM", "netProfitMarginAnnual"),
                    "roe": _first("roeTTM", "roeRfy"),
                    "roa": _first("roaTTM", "roaRfy"),
                    "beta": m.get("beta"),
                    "fifty_two_week_high": m.get("52WeekHigh"),
                    "fifty_two_week_low": m.get("52WeekLow"),
                    "dividend_yield": _first("dividendYieldIndicatedAnnual", "currentDividendYieldTTM"),
                    "debt_to_equity": m.get("totalDebt/totalEquityAnnual"),
                    "current_ratio": _first("currentRatioAnnual", "currentRatioQuarterly"),
                    "free_cash_flow_per_share": _first(
                        "freeCashFlowPerShareTTM", "freeCashFlowPerShareAnnual"
                    ),
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

    async def get_insider_transactions(self, symbol: str, months: int = 6) -> Optional[Dict[str, Any]]:
        """Share-level insider activity, which our EDGAR source cannot provide.

        EDGAR full-text search returns filing metadata only — who filed and
        when — so a Form 4 could be reported but never sized. "An executive
        sold shares" is not information a holder can weigh; "sold 17,557
        shares, 42% of the position" is. Finnhub returns the share counts and
        the holding after the trade, which is what makes the percentage
        computable at all.
        """
        if not self.is_configured():
            return None
        try:
            frm = (datetime.now(timezone.utc) - timedelta(days=months * 30)).strftime("%Y-%m-%d")
            to = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{BASE_URL}/stock/insider-transactions",
                    params={"symbol": symbol, "from": frm, "to": to},
                    headers=self._headers(),
                )
                if resp.status_code != 200:
                    return None
                rows = (resp.json() or {}).get("data") or []

            bought = sold = 0
            recent = []
            for r in rows:
                change = r.get("change")
                if change is None:
                    continue
                change = int(change)
                if change > 0:
                    bought += change
                else:
                    sold += -change
                held_after = r.get("share")
                pct = None
                if change < 0 and held_after is not None:
                    before = int(held_after) + (-change)
                    if before > 0:
                        pct = round(-change / before * 100, 1)
                recent.append({
                    "name": r.get("name"),
                    "change": change,
                    "held_after": held_after,
                    "pct_of_holding": pct,
                    "price": r.get("transactionPrice"),
                    "date": r.get("transactionDate") or r.get("filingDate"),
                })

            recent.sort(key=lambda x: abs(x["change"] or 0), reverse=True)
            return {
                "months": months,
                "filings": len(recent),
                "shares_bought": bought,
                "shares_sold": sold,
                "net_shares": bought - sold,
                "largest": recent[:3],
            }
        except Exception as e:
            logger.debug("Finnhub insider transactions failed", symbol=symbol, error=str(e))
            return None

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
