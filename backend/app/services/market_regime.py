"""
Market regime — is the market as a whole healthy, correcting, or under stress?

Every technical signal is computed on one stock in isolation, so a BUY on NVDA
said nothing about a week in which the whole market fell. This adds the
missing layer: one reading for the market, from three kinds of evidence.

  Trend      S&P 500 (SPY) against its 50- and 200-day averages, and how far
             it is below its one-year high. The classic definitions: 10% down
             is a correction, 20% a bear market.
  Stress     The measures that moved BEFORE the index in past crises:
             high-yield credit spreads (widened for months ahead of 2008),
             the St. Louis Fed Financial Stress Index, the Chicago Fed
             financial conditions index, and VIX. Trend measures confirm a
             fall; these warn of one.
  Breadth    How many of the stocks we analyse trade above their own 200-day
             average. A fall carried by a handful of giants and a fall in
             everything are different markets.

None of this predicts a crash or its timing. It says how much risk there is
right now, which is what a reader deciding whether to keep holding needs.

The reading is deliberately simple — points per condition, three bands — so
that anyone can see why it says what it says. Every confirmed change is also
recorded as an alert outcome on SPY, so whether this detector actually sees
risk, or only makes noise, is measured like everything else.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
import structlog

logger = structlog.get_logger(__name__)

HEALTHY, CORRECTION, STRESS = "HEALTHY", "CORRECTION", "STRESS"
#: Score at or above which the regime is CORRECTION / STRESS.
CORRECTION_AT, STRESS_AT = 3, 6
#: Stress-layer points that force STRESS whatever the trend says: the leading
#: measures flashing together is the case this detector exists for.
STRESS_LAYER_OVERRIDE = 4

#: FRED series: id → (label, max age in days before treated as missing).
FRED_SERIES = {
    "VIXCLS": ("VIX", 7),
    "BAMLH0A0HYM2": ("High-yield credit spread", 7),
    "STLFSI4": ("St. Louis Fed Financial Stress Index", 14),
    "NFCI": ("Chicago Fed Financial Conditions Index", 14),
    "T10Y2Y": ("10Y-2Y Treasury spread", 7),
}

REDIS_KEY = "investment_ai:market_regime"
PENDING_KEY = "investment_ai:market_regime:pending"
#: A change must show on this many consecutive daily readings before it is
#: committed and anyone is told. Markets cross thresholds and back.
CONFIRM_READINGS = 2


async def _fred_history(client: httpx.AsyncClient, series_id: str) -> List[Tuple[str, float]]:
    """All observations of a FRED series as [(date, value)], oldest first."""
    try:
        resp = await client.get("https://fred.stlouisfed.org/graph/fredgraph.csv",
                                params={"id": series_id}, timeout=15)
        if resp.status_code != 200:
            return []
        out = []
        for line in resp.text.strip().split("\n")[1:]:
            parts = line.split(",")
            if len(parts) == 2 and parts[1].strip() not in (".", ""):
                try:
                    out.append((parts[0].strip(), float(parts[1])))
                except ValueError:
                    continue
        return out
    except Exception as exc:
        logger.warning("FRED fetch failed", series=series_id, error=str(exc))
        return []


def _latest(hist: List[Tuple[str, float]], max_age_days: int) -> Optional[float]:
    if not hist:
        return None
    date, value = hist[-1]
    try:
        age = (datetime.now() - datetime.strptime(date, "%Y-%m-%d")).days
        if age > max_age_days:
            return None
    except ValueError:
        return None
    return value


def _ago(hist: List[Tuple[str, float]], observations: int) -> Optional[float]:
    return hist[-1 - observations][1] if len(hist) > observations else None


async def fetch_inputs() -> Dict[str, Any]:
    """Everything the reading is computed from. Missing pieces are None."""
    from app.services.performance_service import spy_closes

    async with httpx.AsyncClient() as client:
        fred_lists = await asyncio.gather(*(_fred_history(client, s) for s in FRED_SERIES))
    fred = dict(zip(FRED_SERIES, fred_lists))

    closes = await spy_closes()
    prices = [v for _, v in sorted(closes.items())]

    inputs: Dict[str, Any] = {
        "spy": prices[-1] if prices else None,
        "spy_ma50": sum(prices[-50:]) / 50 if len(prices) >= 50 else None,
        "spy_ma200": sum(prices[-200:]) / 200 if len(prices) >= 200 else None,
        "spy_high_1y": max(prices[-252:]) if prices else None,
    }
    for sid, (_, max_age) in FRED_SERIES.items():
        inputs[sid] = _latest(fred[sid], max_age)
    # Credit spreads matter most for how fast they widen: about a month back.
    hy = fred["BAMLH0A0HYM2"]
    inputs["hy_spread_1m_ago"] = _ago(hy, 21) if inputs["BAMLH0A0HYM2"] is not None else None
    # The curve's lowest point over the past year: an inversion that has just
    # ended has preceded recessions more reliably than the inversion itself.
    curve = [v for _, v in fred["T10Y2Y"][-252:]]
    inputs["t10y2y_min_1y"] = min(curve) if curve and inputs["T10Y2Y"] is not None else None
    inputs["breadth_pct"] = await _breadth()
    return inputs


async def _breadth() -> Optional[float]:
    """Share of analysed stocks trading above their 200-day average.

    Measured over the live recommendations, the stocks this system keeps a
    fresh technical reading for. A narrower set than the whole market, so it
    needs a reasonable number of readings to mean anything.
    """
    try:
        from sqlalchemy import select
        from app.core.database import AsyncSessionLocal
        from app.db.models.recommendation import Recommendation, RecommendationStatus

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(Recommendation.symbol, Recommendation.technical_analysis).where(
                    Recommendation.status.in_([
                        RecommendationStatus.APPROVED,
                        RecommendationStatus.PRESENTED_TO_USER,
                        RecommendationStatus.ACTIONED,
                    ]))
            )).all()
        seen, above = set(), 0
        for symbol, ta in rows:
            if symbol in seen or not isinstance(ta, dict):
                continue
            price, ma200 = ta.get("current_price"), ta.get("ma_200")
            if not price or not ma200:
                continue
            seen.add(symbol)
            above += 1 if price > ma200 else 0
        return round(above / len(seen) * 100, 1) if len(seen) >= 30 else None
    except Exception as exc:
        logger.warning("breadth failed", error=str(exc))
        return None


def assess(i: Dict[str, Any]) -> Dict[str, Any]:
    """Score the inputs. Pure, so it can be tested against past crises."""
    reasons: List[Dict[str, Any]] = []
    trend = stress = breadth = 0

    def add(layer: str, points: int, en: str, he: str):
        nonlocal trend, stress, breadth
        if layer == "trend":
            trend += points
        elif layer == "stress":
            stress += points
        else:
            breadth += points
        reasons.append({"layer": layer, "points": points, "en": en, "he": he})

    spy, ma50, ma200, high = i.get("spy"), i.get("spy_ma50"), i.get("spy_ma200"), i.get("spy_high_1y")
    if spy and ma200 and spy < ma200:
        add("trend", 2, "S&P 500 is below its 200-day average", "S&P 500 מתחת לממוצע 200 הימים")
    if spy and ma50 and spy < ma50:
        add("trend", 1, "S&P 500 is below its 50-day average", "S&P 500 מתחת לממוצע 50 הימים")
    drawdown = round((high - spy) / high * 100, 1) if spy and high else None
    if drawdown is not None and drawdown >= 20:
        add("trend", 2, f"S&P 500 is {drawdown}% below its one-year high (bear market)",
            f"S&P 500 נמוך ב-{drawdown}% מהשיא השנתי (שוק דובי)")
    elif drawdown is not None and drawdown >= 10:
        add("trend", 1, f"S&P 500 is {drawdown}% below its one-year high (correction)",
            f"S&P 500 נמוך ב-{drawdown}% מהשיא השנתי (תיקון)")

    vix = i.get("VIXCLS")
    if vix is not None and vix >= 35:
        add("stress", 2, f"VIX at {vix:.0f}: extreme fear", f"VIX ב-{vix:.0f}: פחד קיצוני")
    elif vix is not None and vix >= 25:
        add("stress", 1, f"VIX at {vix:.0f}: elevated fear", f"VIX ב-{vix:.0f}: פחד מוגבר")

    hy, hy_prev = i.get("BAMLH0A0HYM2"), i.get("hy_spread_1m_ago")
    if hy is not None and hy >= 7:
        add("stress", 2, f"High-yield credit spread at {hy:.1f}%: credit stress",
            f"מרווח אשראי בתשואה גבוהה {hy:.1f}%: לחץ אשראי")
    elif hy is not None and hy >= 5:
        add("stress", 1, f"High-yield credit spread at {hy:.1f}%: elevated",
            f"מרווח אשראי בתשואה גבוהה {hy:.1f}%: גבוה")
    if hy is not None and hy_prev is not None and hy - hy_prev >= 1.0:
        add("stress", 1, f"Credit spreads widened {hy - hy_prev:.1f} points in a month",
            f"מרווחי האשראי התרחבו ב-{hy - hy_prev:.1f} נקודות בחודש")

    fsi = i.get("STLFSI4")
    if fsi is not None and fsi >= 1.5:
        add("stress", 2, f"Financial stress index at {fsi:.2f}: high", f"מדד הלחץ הפיננסי {fsi:.2f}: גבוה")
    elif fsi is not None and fsi > 0:
        add("stress", 1, f"Financial stress index at {fsi:.2f}: above normal",
            f"מדד הלחץ הפיננסי {fsi:.2f}: מעל הרגיל")

    nfci = i.get("NFCI")
    if nfci is not None and nfci > 0:
        add("stress", 1, f"Financial conditions tighter than average (NFCI {nfci:.2f})",
            f"התנאים הפיננסיים הדוקים מהממוצע (NFCI {nfci:.2f})")

    curve, curve_min = i.get("T10Y2Y"), i.get("t10y2y_min_1y")
    if curve is not None and curve < 0:
        add("stress", 1, f"Yield curve inverted (10Y-2Y {curve:.2f})",
            f"עקום התשואות הפוך (10Y-2Y {curve:.2f})")
    elif curve is not None and curve_min is not None and curve_min <= -0.25:
        add("stress", 1, "Yield curve has just come out of an inversion, which has preceded past recessions",
            "עקום התשואות יצא לאחרונה מהיפוך, מצב שקדם למיתונים בעבר")

    b = i.get("breadth_pct")
    if b is not None and b < 25:
        add("breadth", 2, f"Only {b:.0f}% of analysed stocks are above their 200-day average",
            f"רק {b:.0f}% מהמניות המנותחות מעל ממוצע 200 הימים")
    elif b is not None and b < 40:
        add("breadth", 1, f"{b:.0f}% of analysed stocks are above their 200-day average",
            f"{b:.0f}% מהמניות המנותחות מעל ממוצע 200 הימים")

    score = trend + stress + breadth
    if score >= STRESS_AT or stress >= STRESS_LAYER_OVERRIDE:
        regime = STRESS
    elif score >= CORRECTION_AT:
        regime = CORRECTION
    else:
        regime = HEALTHY

    # A reading built on half its inputs should say so.
    known = sum(1 for k in ("spy_ma200", "VIXCLS", "BAMLH0A0HYM2", "STLFSI4", "NFCI", "breadth_pct")
                if i.get(k) is not None)
    return {
        "regime": regime,
        "score": score,
        "layers": {"trend": trend, "stress": stress, "breadth": breadth},
        "reasons": reasons,
        "drawdown_pct": drawdown,
        "inputs_available": known,
        "inputs": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in i.items()},
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


LABELS = {
    HEALTHY: ("Healthy", "שוק בריא", "🟢"),
    CORRECTION: ("Correction", "תיקון", "🟡"),
    STRESS: ("Stress", "לחץ", "🔴"),
}


async def current(redis_client) -> Optional[Dict[str, Any]]:
    """The last committed reading, or None if none was ever made."""
    import json
    raw = await redis_client.get(REDIS_KEY)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


async def context_line(redis_client=None, buy: bool = False) -> str:
    """One Hebrew sentence on the market for a stock alert, or "" when the
    market is healthy or the regime unknown.

    A buy in a weak market is marked high risk: the stock's own indicators
    cannot tell a falling market from a healthy one. Every other alert gets a
    plain statement of the regime, since it bears on whether to keep holding.
    Never raises: an alert must not be lost to this.
    """
    own = redis_client is None
    try:
        if own:
            import redis.asyncio as aioredis
            from app.core.config import settings
            redis_client = aioredis.from_url(settings.REDIS_URL)
        state = await current(redis_client)
        if not state or state.get("regime") == HEALTHY:
            return ""
        label, emoji = LABELS[state["regime"]][1], LABELS[state["regime"]][2]
        if buy:
            return (f" ⚠️ סיכון גבוה: השוק הכללי במצב {label} {emoji}, ובשוק כזה "
                    f"הסיכון בכל קנייה גבוה מהרגיל.")
        return f" מצב השוק הכללי: {label} {emoji}."
    except Exception:
        return ""
    finally:
        if own and redis_client is not None:
            try:
                await redis_client.aclose()
            except Exception:
                pass
