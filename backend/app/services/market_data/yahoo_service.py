"""
Yahoo Finance Service
Async wrapper around yfinance for global stock data.
"""
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import structlog
import pandas as pd
import yfinance as yf

logger = structlog.get_logger(__name__)


class YahooFinanceService:
    """Async wrapper around yfinance for fetching stock data."""

    def __init__(self):
        self._cache: Dict[str, Any] = {}

    async def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch comprehensive stock info including price and fundamentals.
        Returns normalized dict for use in agent state.
        """
        try:
            ticker_data = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._fetch_ticker_info(symbol)
            )
            return ticker_data
        except Exception as e:
            logger.error("Yahoo Finance get_stock_info failed", symbol=symbol, error=str(e))
            raise

    def _fetch_ticker_info(self, symbol: str) -> Dict[str, Any]:
        """Synchronous fetch - runs in thread pool."""
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}

        # Try to get earnings
        earnings_data = None
        try:
            earnings_hist = ticker.earnings_history
            quarterly_earnings = ticker.quarterly_earnings
            calendar = ticker.calendar

            eps_est = None
            rev_est = None
            earnings_date_str = None

            if calendar is not None and isinstance(calendar, dict):
                eps_est = calendar.get("Earnings Estimate", {}).get(symbol) if isinstance(calendar.get("Earnings Estimate"), dict) else None
                earnings_date = calendar.get("Earnings Date")
                if earnings_date is not None:
                    if hasattr(earnings_date, '__iter__') and not isinstance(earnings_date, str):
                        try:
                            earnings_date_str = str(list(earnings_date)[0])
                        except Exception:
                            pass
                    else:
                        earnings_date_str = str(earnings_date)

            last_eps = info.get("trailingEps")
            eps_estimate = info.get("forwardEps") or eps_est
            eps_surprise_pct = None
            if last_eps and eps_estimate and eps_estimate != 0:
                eps_surprise_pct = ((last_eps - eps_estimate) / abs(eps_estimate)) * 100

            revenue_last = info.get("totalRevenue", 0)
            revenue_estimate = info.get("revenueEstimate", 0) or revenue_last

            earnings_history = []
            if quarterly_earnings is not None and not quarterly_earnings.empty:
                for date, row in quarterly_earnings.tail(8).iterrows():
                    earnings_history.append({
                        "date": str(date),
                        "actual": float(row.get("Earnings", 0) or 0),
                        "estimate": float(row.get("Estimate", 0) or 0),
                    })

            earnings_data = {
                "last_eps": float(last_eps) if last_eps else None,
                "eps_estimate": float(eps_estimate) if eps_estimate else None,
                "eps_surprise_pct": float(eps_surprise_pct) if eps_surprise_pct else None,
                "revenue_last": float(revenue_last) if revenue_last else 0.0,
                "revenue_estimate": float(revenue_estimate) if revenue_estimate else 0.0,
                "revenue_surprise_pct": None,
                "earnings_date": earnings_date_str,
                "earnings_history": earnings_history,
            }
        except Exception as e:
            logger.debug("Earnings fetch partial failure", symbol=symbol, error=str(e))

        return {
            "price": float(info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose") or 0),
            "previous_close": float(info.get("previousClose") or info.get("regularMarketPreviousClose") or 0),
            "volume": int(info.get("volume") or info.get("regularMarketVolume") or 0),
            "avg_volume_30d": int(info.get("averageVolume") or info.get("averageVolume10days") or 0),
            "market_cap": float(info.get("marketCap") or 0),
            "pe_ratio": self._safe_float(info.get("trailingPE")),
            "forward_pe": self._safe_float(info.get("forwardPE")),
            "peg_ratio": self._safe_float(info.get("pegRatio")),
            "price_to_book": self._safe_float(info.get("priceToBook")),
            "price_to_sales": self._safe_float(info.get("priceToSalesTrailing12Months")),
            "debt_to_equity": self._safe_float(info.get("debtToEquity")),
            "current_ratio": self._safe_float(info.get("currentRatio")),
            "quick_ratio": self._safe_float(info.get("quickRatio")),
            "revenue_growth": self._safe_float(info.get("revenueGrowth")),
            "earnings_growth": self._safe_float(info.get("earningsGrowth")),
            "profit_margin": self._safe_float(info.get("profitMargins")),
            "operating_margin": self._safe_float(info.get("operatingMargins")),
            "roe": self._safe_float(info.get("returnOnEquity")),
            "roa": self._safe_float(info.get("returnOnAssets")),
            "free_cash_flow": self._safe_float(info.get("freeCashflow")),
            "dividend_yield": self._safe_float(info.get("dividendYield")),
            "beta": self._safe_float(info.get("beta")),
            "fifty_two_week_high": float(info.get("fiftyTwoWeekHigh") or 0),
            "fifty_two_week_low": float(info.get("fiftyTwoWeekLow") or 0),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "country": info.get("country", "US"),
            "currency": info.get("currency", "USD"),
            "analyst_target_price": self._safe_float(info.get("targetMeanPrice")),
            "analyst_recommendation": info.get("recommendationKey"),
            "institutional_ownership": self._safe_float(info.get("institutionsPercentHeld")),
            "short_interest": self._safe_float(info.get("shortPercentOfFloat")),
            "earnings_data": earnings_data,
            "name": info.get("shortName") or info.get("longName", symbol),
            "exchange": info.get("exchange", "NASDAQ"),
        }

    async def get_historical_prices(self, symbol: str, period: str = "6mo") -> Optional[pd.DataFrame]:
        """Fetch OHLCV historical data."""
        try:
            df = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: yf.download(symbol, period=period, progress=False, auto_adjust=True)
            )
            if df is None or df.empty:
                return None
            # Flatten multi-index if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df
        except Exception as e:
            logger.error("get_historical_prices failed", symbol=symbol, error=str(e))
            return None

    async def get_earnings(self, symbol: str) -> Dict[str, Any]:
        """Fetch earnings history."""
        try:
            def _fetch():
                ticker = yf.Ticker(symbol)
                quarterly = ticker.quarterly_earnings
                annual = ticker.earnings
                result = {"quarterly": [], "annual": []}
                if quarterly is not None and not quarterly.empty:
                    result["quarterly"] = quarterly.reset_index().to_dict(orient="records")
                if annual is not None and not annual.empty:
                    result["annual"] = annual.reset_index().to_dict(orient="records")
                return result
            return await asyncio.get_event_loop().run_in_executor(None, _fetch)
        except Exception as e:
            logger.error("get_earnings failed", symbol=symbol, error=str(e))
            return {"quarterly": [], "annual": []}

    async def search_stocks(self, query: str) -> List[Dict[str, Any]]:
        """Search for stocks by query string."""
        try:
            def _search():
                results = []
                # yfinance doesn't have direct search, use a simple approach
                ticker = yf.Ticker(query.upper())
                info = ticker.info
                if info and info.get("symbol"):
                    results.append({
                        "symbol": info.get("symbol", query.upper()),
                        "name": info.get("shortName") or info.get("longName", ""),
                        "exchange": info.get("exchange", ""),
                        "type": "STOCK",
                        "currency": info.get("currency", "USD"),
                    })
                return results

            return await asyncio.get_event_loop().run_in_executor(None, _search)
        except Exception as e:
            logger.warning("search_stocks failed", query=query, error=str(e))
            return []

    def _safe_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            f = float(value)
            if f != f:  # NaN check
                return None
            return f
        except (TypeError, ValueError):
            return None
