"""
Financial Modeling Prep (FMP) Service
Fallback market data source when Yahoo Finance is blocked on Railway.
Free tier: 250 requests/day.
Endpoints used: /quote, /profile, /ratios-ttm, /key-metrics-ttm, /income-statement
"""
import asyncio
from typing import Any, Dict, List, Optional
import structlog
import httpx

from app.core.config import settings

logger = structlog.get_logger(__name__)

FMP_BASE = "https://financialmodelingprep.com/api/v3"


class FMPService:
    """FMP as fallback data source for US stocks."""

    def _key(self) -> Optional[str]:
        k = settings.FMP_API_KEY
        return k if k and not k.startswith("your_") else None

    async def _get(self, client: httpx.AsyncClient, path: str, params: Dict = None) -> Optional[Any]:
        key = self._key()
        if not key:
            return None
        try:
            p = {"apikey": key, **(params or {})}
            resp = await client.get(f"{FMP_BASE}{path}", params=p, timeout=12)
            if resp.status_code == 200:
                return resp.json()
            logger.debug("FMP non-200", path=path, status=resp.status_code)
        except Exception as e:
            logger.debug("FMP request failed", path=path, error=str(e))
        return None

    async def get_stock_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch comprehensive stock data from FMP.
        Returns dict matching yahoo_service.get_stock_info() field names, or None.
        """
        if not self._key():
            logger.debug("FMP API key not configured — skipping", symbol=symbol)
            return None

        async with httpx.AsyncClient(timeout=15) as client:
            quote_data, profile_data, ratios_data, metrics_data, income_data = await asyncio.gather(
                self._get(client, f"/quote/{symbol}"),
                self._get(client, f"/profile/{symbol}"),
                self._get(client, f"/ratios-ttm/{symbol}"),
                self._get(client, f"/key-metrics-ttm/{symbol}"),
                self._get(client, f"/income-statement/{symbol}", {"limit": 4, "period": "quarter"}),
                return_exceptions=True,
            )

        result: Dict[str, Any] = {}

        # ── Quote ────────────────────────────────────────────────────────────
        q = None
        if isinstance(quote_data, list) and quote_data:
            q = quote_data[0]
        if q:
            result["price"]             = float(q.get("price") or 0)
            result["previous_close"]    = float(q.get("previousClose") or 0)
            result["volume"]            = int(q.get("volume") or 0)
            result["avg_volume_30d"]    = int(q.get("avgVolume") or 0)
            result["market_cap"]        = float(q.get("marketCap") or 0)
            result["fifty_two_week_high"] = float(q.get("yearHigh") or 0)
            result["fifty_two_week_low"]  = float(q.get("yearLow") or 0)
            result["pe_ratio"]          = q.get("pe")
            result["earnings_per_share"] = q.get("eps")
            result["analyst_target_price"] = q.get("priceAvg200")  # rough proxy
            result["name"]              = q.get("name", symbol)

        # ── Profile ──────────────────────────────────────────────────────────
        p = None
        if isinstance(profile_data, list) and profile_data:
            p = profile_data[0]
        if p:
            result["sector"]    = p.get("sector")
            result["industry"]  = p.get("industry")
            result["country"]   = p.get("country", "US")
            result["currency"]  = p.get("currency", "USD")
            result["exchange"]  = p.get("exchangeShortName", "NASDAQ")
            result["beta"]      = p.get("beta")
            result["name"]      = p.get("companyName", result.get("name", symbol))

        # ── Ratios TTM ───────────────────────────────────────────────────────
        r = None
        if isinstance(ratios_data, list) and ratios_data:
            r = ratios_data[0]
        if r:
            result["pe_ratio"]          = result.get("pe_ratio") or r.get("peRatioTTM")
            result["peg_ratio"]         = r.get("pegRatioTTM") or r.get("priceEarningsToGrowthRatioTTM")
            result["price_to_book"]     = r.get("priceToBookRatioTTM")
            result["price_to_sales"]    = r.get("priceToSalesRatioTTM")
            result["debt_to_equity"]    = r.get("debtEquityRatioTTM")
            result["current_ratio"]     = r.get("currentRatioTTM")
            result["quick_ratio"]       = r.get("quickRatioTTM")
            result["profit_margin"]     = r.get("netProfitMarginTTM")
            result["operating_margin"]  = r.get("operatingProfitMarginTTM")
            result["roe"]               = r.get("returnOnEquityTTM")
            result["roa"]               = r.get("returnOnAssetsTTM")
            result["dividend_yield"]    = r.get("dividendYieldTTM")

        # ── Key Metrics TTM ──────────────────────────────────────────────────
        m = None
        if isinstance(metrics_data, list) and metrics_data:
            m = metrics_data[0]
        if m:
            fcf_ps = m.get("freeCashFlowPerShareTTM")
            shares  = float(q.get("sharesOutstanding") or 0) if q else 0
            if fcf_ps and shares:
                result["free_cash_flow"] = float(fcf_ps) * shares
            result["institutional_ownership"] = m.get("roicTTM")  # not exact but available
            result["short_interest"] = None  # FMP free doesn't expose this

        # ── Income Statements: compute revenue/earnings growth ────────────────
        if isinstance(income_data, list) and len(income_data) >= 2:
            try:
                latest = income_data[0]
                prior  = income_data[1]
                rev_latest = float(latest.get("revenue") or 0)
                rev_prior  = float(prior.get("revenue") or 1)
                if rev_prior:
                    result["revenue_growth"] = (rev_latest - rev_prior) / abs(rev_prior)
                eps_latest = float(latest.get("eps") or 0)
                eps_prior  = float(prior.get("eps") or 0)
                if eps_prior and eps_prior != 0:
                    result["earnings_growth"] = (eps_latest - eps_prior) / abs(eps_prior)
                # Earnings data block
                result["earnings_data"] = {
                    "last_eps":           eps_latest,
                    "eps_estimate":       None,
                    "eps_surprise_pct":   None,
                    "revenue_last":       rev_latest,
                    "revenue_estimate":   None,
                    "revenue_surprise_pct": None,
                    "earnings_date":      latest.get("date"),
                    "earnings_history":   [],
                }
            except Exception as exc:
                logger.debug("FMP income statement parse error", error=str(exc))

        # Guard: only return if we have a meaningful price
        if not result.get("price") or result["price"] == 0:
            logger.debug("FMP returned zero price — discarding", symbol=symbol)
            return None

        logger.info("FMP data fetched successfully", symbol=symbol, price=result["price"],
                    sector=result.get("sector"), pe=result.get("pe_ratio"))
        return result

    async def get_historical_prices(self, symbol: str, limit: int = 180) -> Optional[List[Dict]]:
        """Fetch daily OHLCV bars. Returns list of {date, open, high, low, close, volume}."""
        if not self._key():
            return None
        async with httpx.AsyncClient(timeout=15) as client:
            data = await self._get(client, f"/historical-price-full/{symbol}", {"serietype": "line"})
        if not data or not isinstance(data, dict):
            return None
        bars = data.get("historical", [])[:limit]
        if not bars:
            return None
        # Normalize to pandas-friendly format
        return [
            {
                "date": b["date"], "open": b.get("open", b.get("close")),
                "high": b.get("high", b.get("close")), "low": b.get("low", b.get("close")),
                "close": b["close"], "volume": b.get("volume", 0),
            }
            for b in bars if b.get("close")
        ]


_fmp_service: Optional[FMPService] = None


def get_fmp_service() -> FMPService:
    global _fmp_service
    if _fmp_service is None:
        _fmp_service = FMPService()
    return _fmp_service
