"""
Alpaca Markets Service
- Market data: reliable US stock prices via Alpaca Data API (free IEX feed)
- Paper trading: auto-execute recommendations on Alpaca paper account
  Set ALPACA_API_KEY + ALPACA_API_SECRET in Railway to enable.
  Set ALPACA_PAPER=true (default) for paper trading.
"""
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import structlog
import httpx

from app.core.config import settings

logger = structlog.get_logger(__name__)

PAPER_BASE = "https://paper-api.alpaca.markets/v2"
LIVE_BASE  = "https://api.alpaca.markets/v2"
DATA_BASE  = "https://data.alpaca.markets/v2"


class AlpacaService:
    """Alpaca for US market data and paper trading. Uses plain httpx — no SDK needed."""

    def _headers(self) -> Optional[Dict[str, str]]:
        key = settings.ALPACA_API_KEY
        secret = settings.ALPACA_API_SECRET
        if not key or not secret or key.startswith("your_"):
            return None
        return {
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "accept": "application/json",
            "content-type": "application/json",
        }

    def _trade_base(self) -> str:
        return PAPER_BASE if settings.ALPACA_PAPER else LIVE_BASE

    # ── Market Data ──────────────────────────────────────────────────────────

    async def get_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch latest price snapshot from Alpaca Data API.
        Returns dict with price/volume/OHLCV, or None if unavailable.
        """
        headers = self._headers()
        if not headers:
            return None
        try:
            async with httpx.AsyncClient(timeout=10, headers=headers) as client:
                resp = await client.get(f"{DATA_BASE}/stocks/{symbol}/snapshot")
                if resp.status_code != 200:
                    logger.debug("Alpaca snapshot failed", symbol=symbol, status=resp.status_code)
                    return None
                data = resp.json()
                lt = data.get("latestTrade", {})
                lq = data.get("latestQuote", {})
                bar = data.get("dailyBar", {})
                prev_bar = data.get("prevDailyBar", {})
                return {
                    "price":          float(lt.get("p") or bar.get("c") or 0),
                    "previous_close": float(prev_bar.get("c") or 0),
                    "volume":         int(bar.get("v") or 0),
                    "open":           float(bar.get("o") or 0),
                    "high":           float(bar.get("h") or 0),
                    "low":            float(bar.get("l") or 0),
                    "bid":            float(lq.get("bp") or 0),
                    "ask":            float(lq.get("ap") or 0),
                }
        except Exception as e:
            logger.debug("Alpaca snapshot error", symbol=symbol, error=str(e))
            return None

    async def get_historical_bars(self, symbol: str, timeframe: str = "1Day",
                                   limit: int = 200) -> Optional[List[Dict]]:
        """Fetch historical OHLCV bars for technical analysis."""
        headers = self._headers()
        if not headers:
            return None
        try:
            async with httpx.AsyncClient(timeout=15, headers=headers) as client:
                resp = await client.get(
                    f"{DATA_BASE}/stocks/{symbol}/bars",
                    params={"timeframe": timeframe, "limit": limit, "sort": "asc"},
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()
                bars = data.get("bars", [])
                return [
                    {
                        "date":   b["t"][:10],
                        "open":   b["o"], "high": b["h"],
                        "low":    b["l"], "close": b["c"],
                        "volume": b["v"],
                    }
                    for b in bars
                ]
        except Exception as e:
            logger.debug("Alpaca bars error", symbol=symbol, error=str(e))
            return None

    # ── Paper Account ────────────────────────────────────────────────────────

    async def get_account(self) -> Optional[Dict[str, Any]]:
        """Get paper trading account equity and cash."""
        headers = self._headers()
        if not headers:
            return None
        try:
            async with httpx.AsyncClient(timeout=10, headers=headers) as client:
                resp = await client.get(f"{self._trade_base()}/account")
                if resp.status_code == 200:
                    d = resp.json()
                    return {
                        "equity":        float(d.get("equity") or 0),
                        "cash":          float(d.get("cash") or 0),
                        "buying_power":  float(d.get("buying_power") or 0),
                        "portfolio_value": float(d.get("portfolio_value") or 0),
                        "pnl":           float(d.get("equity", 0)) - float(d.get("last_equity", d.get("equity", 0))),
                        "status":        d.get("status"),
                        "paper":         settings.ALPACA_PAPER,
                    }
        except Exception as e:
            logger.debug("Alpaca account error", error=str(e))
        return None

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get open paper trading positions."""
        headers = self._headers()
        if not headers:
            return []
        try:
            async with httpx.AsyncClient(timeout=10, headers=headers) as client:
                resp = await client.get(f"{self._trade_base()}/positions")
                if resp.status_code == 200:
                    return [
                        {
                            "symbol":        p["symbol"],
                            "qty":           float(p["qty"]),
                            "side":          p["side"],
                            "avg_entry":     float(p["avg_entry_price"]),
                            "current_price": float(p["current_price"]),
                            "market_value":  float(p["market_value"]),
                            "unrealized_pl": float(p["unrealized_pl"]),
                            "unrealized_plpc": float(p["unrealized_plpc"]) * 100,
                        }
                        for p in resp.json()
                    ]
        except Exception as e:
            logger.debug("Alpaca positions error", error=str(e))
        return []

    async def get_closed_orders(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent filled orders for performance tracking."""
        headers = self._headers()
        if not headers:
            return []
        try:
            async with httpx.AsyncClient(timeout=10, headers=headers) as client:
                resp = await client.get(
                    f"{self._trade_base()}/orders",
                    params={"status": "filled", "limit": limit, "direction": "desc"},
                )
                if resp.status_code == 200:
                    return [
                        {
                            "symbol":     o["symbol"],
                            "side":       o["side"],
                            "qty":        float(o.get("filled_qty") or 0),
                            "price":      float(o.get("filled_avg_price") or 0),
                            "filled_at":  o.get("filled_at"),
                            "order_id":   o["id"],
                        }
                        for o in resp.json() if o.get("status") == "filled"
                    ]
        except Exception as e:
            logger.debug("Alpaca orders error", error=str(e))
        return []

    # ── Paper Trade Execution ────────────────────────────────────────────────

    async def place_paper_trade(
        self,
        symbol: str,
        side: str,           # "buy" or "sell"
        notional: float,     # dollar amount to trade
        recommendation_id: Optional[int] = None,
        confidence: float = 50.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Place a paper trade order by dollar notional amount.
        Called automatically when Senior Committee approves a recommendation.
        Returns order dict or None on failure.
        """
        headers = self._headers()
        if not headers:
            return None

        if notional < 1:
            logger.debug("Alpaca paper trade skipped — notional too small", notional=notional)
            return None

        order_data = {
            "symbol":        symbol,
            "notional":      str(round(notional, 2)),
            "side":          side,
            "type":          "market",
            "time_in_force": "day",
            "client_order_id": f"ai-rec-{recommendation_id or 'manual'}-{int(datetime.now(timezone.utc).timestamp())}",
        }

        try:
            async with httpx.AsyncClient(timeout=15, headers=headers) as client:
                resp = await client.post(f"{self._trade_base()}/orders", json=order_data)
                if resp.status_code in (200, 201):
                    order = resp.json()
                    logger.info(
                        "Alpaca paper trade placed",
                        symbol=symbol, side=side, notional=notional,
                        order_id=order.get("id"), confidence=confidence,
                    )
                    return {
                        "order_id":   order.get("id"),
                        "symbol":     symbol,
                        "side":       side,
                        "notional":   notional,
                        "status":     order.get("status"),
                        "created_at": order.get("created_at"),
                        "paper":      settings.ALPACA_PAPER,
                    }
                else:
                    err = resp.json()
                    logger.warning(
                        "Alpaca paper trade failed",
                        symbol=symbol, side=side,
                        status=resp.status_code, error=err.get("message"),
                    )
        except Exception as e:
            logger.warning("Alpaca paper trade error", symbol=symbol, error=str(e))
        return None


_alpaca_service: Optional[AlpacaService] = None


def get_alpaca_service() -> AlpacaService:
    global _alpaca_service
    if _alpaca_service is None:
        _alpaca_service = AlpacaService()
    return _alpaca_service
