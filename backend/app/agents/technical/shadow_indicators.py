"""
Indicators computed in shadow: recorded with every analysis and every alert,
given no weight in the signal.

Each answers a question the existing indicators do not, rather than restating
RSI or a moving average a different way:

  Relative strength   Is the stock doing better than the market, and than its
                      own sector? A stock holding up while the index falls is
                      a different buy from one falling with it.
  ADX                 Is there a trend at all? The trend gate assumes one;
                      ADX says when that assumption holds.
  Money flow          Is volume coming in on up days (accumulation) or on down
                      days (distribution)? Chaikin Money Flow and the slope of
                      On-Balance Volume.
  Weekly trend        Does the weekly chart agree with the daily signal?

Whether any of them deserves weight is decided by the alert-outcome data,
split by each condition (see /market/diagnostics/alert-outcomes), not here.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger(__name__)

#: Yahoo sector name → SPDR sector ETF.
SECTOR_ETF = {
    "Technology": "XLK", "Information Technology": "XLK",
    "Financial Services": "XLF", "Financials": "XLF",
    "Healthcare": "XLV", "Health Care": "XLV",
    "Consumer Cyclical": "XLY", "Consumer Discretionary": "XLY",
    "Consumer Defensive": "XLP", "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Basic Materials": "XLB", "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Communication Services": "XLC",
}

_BENCH_CACHE: Dict[str, tuple] = {}
_BENCH_TTL = 6 * 3600


async def benchmark_closes(symbol: str) -> Optional[pd.Series]:
    """Daily closes of an index or sector ETF, cached for six hours: every
    analysis in a scan compares against the same few benchmarks."""
    hit = _BENCH_CACHE.get(symbol)
    if hit and time.time() - hit[0] < _BENCH_TTL:
        return hit[1]
    try:
        from app.services.market_data.yahoo_service import YahooFinanceService
        df = await YahooFinanceService().get_historical_prices(symbol, "1y")
        series = df["Close"].dropna() if df is not None and not df.empty else None
    except Exception as exc:
        logger.debug("benchmark fetch failed", symbol=symbol, error=str(exc))
        series = None
    if series is None and symbol == "SPY":
        from app.services.performance_service import spy_closes
        closes = await spy_closes()
        if closes:
            series = pd.Series(closes).sort_index()
            series.index = pd.to_datetime(series.index)
    if series is not None:
        _BENCH_CACHE[symbol] = (time.time(), series)
    return series


def _ret(series: pd.Series, days: int) -> Optional[float]:
    if series is None or len(series) <= days:
        return None
    a, b = float(series.iloc[-1 - days]), float(series.iloc[-1])
    return (b - a) / a * 100 if a else None


def adx(df: pd.DataFrame, period: int = 14) -> Dict[str, Optional[float]]:
    """Wilder's ADX with +DI / -DI."""
    if len(df) < period * 2 + 1:
        return {"adx_14": None, "plus_di": None, "minus_di": None}
    high, low, close = df["High"], df["Low"], df["Close"]
    up, down = high.diff(), -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    alpha = 1 / period
    atr = tr.ewm(alpha=alpha, adjust=False).mean()
    pdi = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=alpha, adjust=False).mean() / atr
    mdi = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=alpha, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    a = dx.ewm(alpha=alpha, adjust=False).mean()
    last = lambda s: round(float(s.iloc[-1]), 1) if pd.notna(s.iloc[-1]) else None
    return {"adx_14": last(a), "plus_di": last(pdi), "minus_di": last(mdi)}


def money_flow(df: pd.DataFrame) -> Dict[str, Optional[float]]:
    """Chaikin Money Flow (20) and the 20-day slope of On-Balance Volume,
    scaled by average volume so stocks of different size compare."""
    out: Dict[str, Optional[float]] = {"cmf_20": None, "obv_slope_20": None}
    if len(df) < 25:
        return out
    high, low, close, vol = df["High"], df["Low"], df["Close"], df["Volume"].astype(float)
    rng = (high - low).replace(0, np.nan)
    mfv = ((close - low) - (high - close)) / rng * vol
    v20 = vol.tail(20).sum()
    if v20:
        out["cmf_20"] = round(float(mfv.tail(20).sum() / v20), 3)
    obv = (np.sign(close.diff()).fillna(0) * vol).cumsum()
    avg_vol = vol.tail(20).mean()
    if avg_vol:
        slope = np.polyfit(range(20), obv.tail(20).values, 1)[0]
        out["obv_slope_20"] = round(float(slope / avg_vol), 3)
    return out


def weekly(df: pd.DataFrame) -> Dict[str, Any]:
    """The daily bars resampled to weeks: close against the 10- and 30-week
    averages (about 50 and 150 days)."""
    out: Dict[str, Any] = {"weekly_trend": None, "weekly_above_10w": None, "weekly_above_30w": None}
    try:
        idx = df.index if isinstance(df.index, pd.DatetimeIndex) else pd.to_datetime(df.index)
        w = df["Close"].copy()
        w.index = idx
        w = w.resample("W-FRI").last().dropna()
    except Exception:
        return out
    if len(w) < 30:
        return out
    last = float(w.iloc[-1])
    ma10, ma30 = float(w.tail(10).mean()), float(w.tail(30).mean())
    out["weekly_above_10w"] = last > ma10
    out["weekly_above_30w"] = last > ma30
    out["weekly_trend"] = ("UP" if last > ma10 > ma30 else
                           "DOWN" if last < ma10 < ma30 else "MIXED")
    return out


async def compute(df: pd.DataFrame, sector: Optional[str] = None) -> Dict[str, Any]:
    """All shadow indicators for one stock. Never raises."""
    out: Dict[str, Any] = {}
    for fn in (adx, money_flow, weekly):
        try:
            out.update(fn(df))
        except Exception as exc:
            logger.debug("shadow indicator failed", fn=fn.__name__, error=str(exc))
    try:
        close = df["Close"]
        for label, days in (("1m", 21), ("3m", 63)):
            stock = _ret(close, days)
            spy = _ret(await benchmark_closes("SPY"), days)
            out[f"rs_spy_{label}"] = round(stock - spy, 2) if stock is not None and spy is not None else None
        etf = SECTOR_ETF.get(sector or "")
        if etf:
            stock, sec = _ret(close, 63), _ret(await benchmark_closes(etf), 63)
            out["sector_etf"] = etf
            out["rs_sector_3m"] = round(stock - sec, 2) if stock is not None and sec is not None else None
    except Exception as exc:
        logger.debug("relative strength failed", error=str(exc))
    return out


def conditions(shadow: Optional[Dict[str, Any]]) -> Dict[str, Optional[bool]]:
    """Yes/no readings the outcome report splits by. None when unknown."""
    s = shadow or {}
    def gt(k, v):
        return None if s.get(k) is None else s[k] > v
    return {
        "beats_market_3m": gt("rs_spy_3m", 0),
        "beats_sector_3m": gt("rs_sector_3m", 0),
        "strong_trend_adx25": gt("adx_14", 25),
        "money_flowing_in": gt("cmf_20", 0),
        "weekly_uptrend": None if s.get("weekly_trend") is None else s["weekly_trend"] == "UP",
        "squeeze_risk": None if s.get("squeeze_level") is None else s["squeeze_level"] != "NONE",
    }
