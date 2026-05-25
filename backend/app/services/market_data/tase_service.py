"""
TASE (Tel Aviv Stock Exchange) Service
Fetches data from the Maya TASE API and maya.tase.co.il.
Handles Hebrew company names and ILS currency.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import structlog
import httpx
import pandas as pd

from app.core.config import settings

logger = structlog.get_logger(__name__)

MAYA_API_BASE = "https://mayaapi.tase.co.il/api"
TASE_API_BASE = "https://api.tase.co.il/api"


class TASEService:
    """
    Service for fetching data from the Tel Aviv Stock Exchange.
    Uses the Maya API (mayaapi.tase.co.il) and TASE public API.
    """

    def __init__(self):
        self._headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Maya-With": "allow",
        }
        self._timeout = httpx.Timeout(30.0)

    async def get_tase_stock_info(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch comprehensive stock info for an Israeli stock.
        symbol can be a stock number (e.g., "1082373") or ticker.
        """
        try:
            # Try to resolve symbol to TASE security number
            security_id = await self._resolve_symbol(symbol)

            async with httpx.AsyncClient(timeout=self._timeout, headers=self._headers) as client:
                # Fetch stock details
                tasks = [
                    self._fetch_stock_details(client, security_id),
                    self._fetch_stock_financials(client, security_id),
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

            details = results[0] if not isinstance(results[0], Exception) else {}
            financials = results[1] if not isinstance(results[1], Exception) else {}

            return self._normalize_tase_data(symbol, details, financials)

        except Exception as e:
            logger.error("TASE get_tase_stock_info failed", symbol=symbol, error=str(e))
            return self._empty_tase_data(symbol)

    async def _resolve_symbol(self, symbol: str) -> str:
        """Resolve a stock ticker to TASE security ID."""
        # If it looks like a numeric ID, use directly
        if symbol.isdigit():
            return symbol

        try:
            async with httpx.AsyncClient(timeout=self._timeout, headers=self._headers) as client:
                resp = await client.get(
                    f"{MAYA_API_BASE}/company/companysearch",
                    params={"q": symbol, "lang": "he"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("Results") or data.get("results") or []
                    if results:
                        first = results[0]
                        return str(first.get("SecurityId") or first.get("securityId") or symbol)
        except Exception:
            pass

        return symbol

    async def _fetch_stock_details(self, client: httpx.AsyncClient, security_id: str) -> Dict[str, Any]:
        """Fetch current stock price and basic details from TASE."""
        try:
            resp = await client.get(
                f"{MAYA_API_BASE}/stock/getstocksummary",
                params={"SecurityId": security_id, "lang": "he"},
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.debug("TASE stock details fetch failed", security_id=security_id, error=str(e))
        return {}

    async def _fetch_stock_financials(self, client: httpx.AsyncClient, security_id: str) -> Dict[str, Any]:
        """Fetch financial data for the stock."""
        try:
            resp = await client.get(
                f"{MAYA_API_BASE}/stock/stockfinancialdata",
                params={"SecurityId": security_id, "lang": "he"},
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.debug("TASE financials fetch failed", security_id=security_id, error=str(e))
        return {}

    def _normalize_tase_data(
        self,
        symbol: str,
        details: Dict[str, Any],
        financials: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Normalize TASE API response to standard format."""
        # Extract nested data
        stock_data = details.get("StockData") or details.get("stockData") or details
        fin_data = financials.get("FinancialData") or financials.get("financialData") or financials

        price = float(stock_data.get("LastPrice") or stock_data.get("lastPrice") or 0)
        prev_close = float(stock_data.get("BasePrice") or stock_data.get("basePrice") or price)
        volume = int(stock_data.get("TradeVolume") or stock_data.get("tradeVolume") or 0)
        market_cap = float(stock_data.get("MarketCap") or stock_data.get("marketCap") or 0)
        name_he = stock_data.get("SecName") or stock_data.get("secName") or symbol
        name_en = stock_data.get("SecNameEng") or stock_data.get("secNameEng") or symbol

        pe_ratio = self._safe_float(fin_data.get("PE") or fin_data.get("pe"))
        eps = self._safe_float(fin_data.get("EPS") or fin_data.get("eps"))
        book_value = self._safe_float(fin_data.get("BookValue") or fin_data.get("bookValue"))
        high_52w = self._safe_float(stock_data.get("High52W") or stock_data.get("high52W")) or price
        low_52w = self._safe_float(stock_data.get("Low52W") or stock_data.get("low52W")) or price

        return {
            "price": price,
            "previous_close": prev_close,
            "volume": volume,
            "avg_volume_30d": volume,
            "market_cap": market_cap,
            "pe_ratio": pe_ratio,
            "forward_pe": None,
            "peg_ratio": None,
            "price_to_book": self._safe_float(fin_data.get("PB") or fin_data.get("pb")),
            "price_to_sales": None,
            "debt_to_equity": self._safe_float(fin_data.get("DebtToEquity")),
            "current_ratio": None,
            "quick_ratio": None,
            "revenue_growth": None,
            "earnings_growth": None,
            "profit_margin": self._safe_float(fin_data.get("NetProfitMargin")),
            "operating_margin": None,
            "roe": self._safe_float(fin_data.get("ROE") or fin_data.get("roe")),
            "roa": None,
            "free_cash_flow": None,
            "dividend_yield": self._safe_float(fin_data.get("DividendYield")),
            "beta": None,
            "fifty_two_week_high": high_52w,
            "fifty_two_week_low": low_52w,
            "earnings_data": {
                "last_eps": eps,
                "eps_estimate": None,
                "eps_surprise_pct": None,
                "revenue_last": 0.0,
                "revenue_estimate": 0.0,
                "revenue_surprise_pct": None,
                "earnings_date": None,
                "earnings_history": [],
            },
            "sector": stock_data.get("Sector") or "General",
            "industry": None,
            "country": "IL",
            "currency": "ILS",
            "analyst_target_price": None,
            "analyst_recommendation": None,
            "institutional_ownership": None,
            "short_interest": None,
            "name": name_en,
            "name_hebrew": name_he,
            "exchange": "TASE",
        }

    async def get_tase_historical(self, symbol: str, days: int = 180) -> Optional[pd.DataFrame]:
        """Fetch historical price data for TASE stock."""
        try:
            security_id = await self._resolve_symbol(symbol)
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

            async with httpx.AsyncClient(timeout=self._timeout, headers=self._headers) as client:
                resp = await client.get(
                    f"{MAYA_API_BASE}/stock/stocktradehistory",
                    params={
                        "SecurityId": security_id,
                        "StartDate": start_date,
                        "EndDate": end_date,
                        "lang": "he",
                    },
                )

                if resp.status_code == 200:
                    data = resp.json()
                    trades = data.get("TradeHistory") or data.get("tradeHistory") or []

                    if not trades:
                        return None

                    records = []
                    for item in trades:
                        date_str = item.get("TrdDate") or item.get("trdDate") or item.get("date")
                        records.append({
                            "Date": pd.to_datetime(date_str),
                            "Open": float(item.get("OpenPrice") or item.get("openPrice") or 0),
                            "High": float(item.get("MaxPrice") or item.get("maxPrice") or 0),
                            "Low": float(item.get("MinPrice") or item.get("minPrice") or 0),
                            "Close": float(item.get("ClosePrice") or item.get("closePrice") or 0),
                            "Volume": int(item.get("Volume") or item.get("volume") or 0),
                        })

                    if not records:
                        return None

                    df = pd.DataFrame(records)
                    df = df.set_index("Date").sort_index()
                    df = df.replace(0, pd.NA).ffill()
                    return df

        except Exception as e:
            logger.error("TASE get_tase_historical failed", symbol=symbol, error=str(e))

        return None

    async def search_tase(self, query: str) -> List[Dict[str, Any]]:
        """Search for TASE stocks by name or symbol."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout, headers=self._headers) as client:
                resp = await client.get(
                    f"{MAYA_API_BASE}/company/companysearch",
                    params={"q": query, "lang": "he"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("Results") or data.get("results") or []
                    return [
                        {
                            "symbol": str(r.get("SecurityId") or r.get("securityId", "")),
                            "name": r.get("SecNameEng") or r.get("secNameEng", ""),
                            "name_hebrew": r.get("SecName") or r.get("secName", ""),
                            "exchange": "TASE",
                            "type": "STOCK",
                            "currency": "ILS",
                            "sector": r.get("Sector", ""),
                        }
                        for r in results[:20]
                    ]
        except Exception as e:
            logger.error("TASE search failed", query=query, error=str(e))
        return []

    def _empty_tase_data(self, symbol: str) -> Dict[str, Any]:
        return {
            "price": 0.0,
            "previous_close": 0.0,
            "volume": 0,
            "avg_volume_30d": 0,
            "market_cap": 0.0,
            "country": "IL",
            "currency": "ILS",
            "exchange": "TASE",
            "fifty_two_week_high": 0.0,
            "fifty_two_week_low": 0.0,
            "name": symbol,
        }

    def _safe_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            f = float(value)
            return None if f != f else f
        except (TypeError, ValueError):
            return None
