"""
Short-squeeze risk.

A heavily shorted stock can rise far beyond anything its business explains
when the short sellers are forced to buy back at once, as GameStop did in
January 2021. That is not predictable from the chart or the results, and
most heavily shorted stocks never squeeze; plenty simply keep falling. What
can be said is that the stock is exposed to an extreme move, in either
direction. That is what this reports: a risk tag, never a buy signal.

Readings: short interest as a share of the float, days to cover (shares
short over average daily volume), the month-on-month change in shares short,
and whether a squeeze looks to be under way (a volume surge with a sharp
rise).
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger(__name__)

NONE, ELEVATED, HIGH = "NONE", "ELEVATED", "HIGH"
_CACHE_KEY = "investment_ai:short_data:"
_CACHE_TTL = 24 * 3600  # short interest is published twice a month


def assess(short_pct: Optional[float], days_to_cover: Optional[float],
           short_change_pct: Optional[float], volume_ratio: Optional[float],
           change_5d_pct: Optional[float]) -> Dict[str, Any]:
    """short_pct is a percentage of float (25 means 25%). Pure, testable."""
    points, reasons = 0, []
    if short_pct is None:
        return {"level": NONE, "points": 0, "reasons": [], "short_pct_float": None}
    if short_pct >= 20:
        points += 2
        reasons.append(f"{short_pct:.0f}% of the float is sold short")
    elif short_pct >= 10:
        points += 1
        reasons.append(f"{short_pct:.0f}% of the float is sold short")
    if days_to_cover is not None and days_to_cover >= 7:
        points += 2
        reasons.append(f"{days_to_cover:.1f} days to cover")
    elif days_to_cover is not None and days_to_cover >= 4:
        points += 1
        reasons.append(f"{days_to_cover:.1f} days to cover")
    if short_change_pct is not None and short_change_pct >= 20 and short_pct >= 10:
        points += 1
        reasons.append(f"shares short up {short_change_pct:.0f}% in a month")
    underway = (short_pct >= 10 and volume_ratio is not None and volume_ratio >= 3
                and change_5d_pct is not None and change_5d_pct >= 15)
    if underway:
        points += 1
        reasons.append("volume surge with a sharp rise: a squeeze may be under way")

    level = (HIGH if points >= 4 and short_pct >= 15 else
             ELEVATED if points >= 2 and short_pct >= 10 else NONE)
    return {"level": level, "points": points, "reasons": reasons,
            "short_pct_float": round(short_pct, 1),
            "days_to_cover": round(days_to_cover, 1) if days_to_cover is not None else None,
            "underway": underway}


async def short_data(symbol: str) -> Dict[str, Optional[float]]:
    """Short interest for a symbol, from Redis when fetched in the last day."""
    import redis.asyncio as aioredis
    from app.core.config import settings

    r = aioredis.from_url(settings.REDIS_URL)
    try:
        raw = await r.get(_CACHE_KEY + symbol)
        if raw:
            return json.loads(raw)
        from app.services.market_data.yahoo_service import YahooFinanceService
        info = await YahooFinanceService().get_stock_info(symbol)
        short = info.get("short_interest")
        prior, now = info.get("shares_short_prior_month"), info.get("shares_short")
        data = {
            # Yahoo gives a fraction (0.25 for 25%, 1.4 for 140%); report a percentage.
            "short_pct": short * 100 if short is not None else None,
            "days_to_cover": info.get("short_ratio"),
            "short_change_pct": ((now - prior) / prior * 100) if now and prior else None,
        }
        await r.set(_CACHE_KEY + symbol, json.dumps(data), ex=_CACHE_TTL)
        return data
    except Exception as exc:
        logger.debug("short data unavailable", symbol=symbol, error=str(exc))
        return {}
    finally:
        await r.aclose()


HE_LINE = " ⚡ סיכון לשורט סקוויז: הרבה מניות בשורט, ותנודה קיצונית אפשרית לשני הכיוונים."
