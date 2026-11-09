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
CORRECTION_AT, STRESS_AT = 3, 7
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
    # Global: a crisis need not start in the US.
    "BAMLHE00EHYIOAS": ("Euro high-yield credit spread", 7),
    "DTWEXBGS": ("Broad US dollar index", 10),
    "DEXJPUS": ("Japanese yen per US dollar", 10),
}

#: Regions read through their US-listed ETFs (dollar prices, one data path).
REGION_ETFS = {"europe": "VGK", "japan": "EWJ", "china": "MCHI", "emerging": "EEM"}
SMALL_CAPS_ETF = "IWM"

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

    # Global layer. The dollar and the yen matter for how fast they move:
    # money runs to the dollar in a crisis, and a sudden jump in the yen was
    # the August 2024 carry-trade unwind (Japan fell 12% in a day).
    def _move_1m(series_id: str) -> Optional[float]:
        h = fred[series_id]
        now_v, then_v = (h[-1][1] if h else None), _ago(h, 21)
        if inputs.get(series_id) is None or not then_v:
            return None
        return (now_v - then_v) / then_v * 100
    inputs["dollar_1m_pct"] = _move_1m("DTWEXBGS")
    jpy = _move_1m("DEXJPUS")
    inputs["yen_1m_pct"] = -jpy if jpy is not None else None  # fewer yen per dollar = yen up

    from app.agents.technical.shadow_indicators import benchmark_closes
    for region, etf in {**REGION_ETFS, "smallcaps": SMALL_CAPS_ETF}.items():
        vs200 = dd = None
        try:
            closes = await benchmark_closes(etf)
            if closes is not None and len(closes) >= 200:
                last = float(closes.iloc[-1])
                ma200 = float(closes.tail(200).mean())
                high = float(closes.tail(252).max())
                vs200 = round((last - ma200) / ma200 * 100, 1)
                dd = round((high - last) / high * 100, 1)
        except Exception as exc:
            logger.debug("region fetch failed", etf=etf, error=str(exc))
        inputs[f"{region}_vs200"] = vs200
        inputs[f"{region}_drawdown"] = dd
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
    trend = stress = breadth = global_ = 0

    def add(layer: str, points: int, en: str, he: str, code: str = "", **vars_):
        nonlocal trend, stress, breadth, global_
        if layer == "trend":
            trend += points
        elif layer == "stress":
            stress += points
        elif layer == "global":
            global_ += points
        else:
            breadth += points
        # `code` and `vars` let the app show the reason in any language.
        reasons.append({"layer": layer, "points": points, "en": en, "he": he,
                        "code": code, "vars": vars_})

    spy, ma50, ma200, high = i.get("spy"), i.get("spy_ma50"), i.get("spy_ma200"), i.get("spy_high_1y")
    if spy and ma200 and spy < ma200:
        add("trend", 2, "S&P 500 is below its 200-day average", "S&P 500 מתחת לממוצע 200 הימים", "spy_below_200")
    if spy and ma50 and spy < ma50:
        add("trend", 1, "S&P 500 is below its 50-day average", "S&P 500 מתחת לממוצע 50 הימים", "spy_below_50")
    drawdown = round((high - spy) / high * 100, 1) if spy and high else None
    if drawdown is not None and drawdown >= 20:
        add("trend", 2, f"S&P 500 is {drawdown}% below its one-year high (bear market)",
            f"S&P 500 נמוך ב-{drawdown}% מהשיא השנתי (שוק דובי)", "drawdown_bear", pct=drawdown)
    elif drawdown is not None and drawdown >= 10:
        add("trend", 1, f"S&P 500 is {drawdown}% below its one-year high (correction)",
            f"S&P 500 נמוך ב-{drawdown}% מהשיא השנתי (תיקון)", "drawdown_correction", pct=drawdown)

    vix = i.get("VIXCLS")
    if vix is not None and vix >= 35:
        add("stress", 2, f"VIX at {vix:.0f}: extreme fear", f"VIX ב-{vix:.0f}: פחד קיצוני", "vix_extreme", v=round(vix))
    elif vix is not None and vix >= 25:
        add("stress", 1, f"VIX at {vix:.0f}: elevated fear", f"VIX ב-{vix:.0f}: פחד מוגבר", "vix_elevated", v=round(vix))

    hy, hy_prev = i.get("BAMLH0A0HYM2"), i.get("hy_spread_1m_ago")
    if hy is not None and hy >= 7:
        add("stress", 2, f"High-yield credit spread at {hy:.1f}%: credit stress",
            f"מרווח אשראי בתשואה גבוהה {hy:.1f}%: לחץ אשראי", "hy_stress", v=round(hy, 1))
    elif hy is not None and hy >= 5:
        add("stress", 1, f"High-yield credit spread at {hy:.1f}%: elevated",
            f"מרווח אשראי בתשואה גבוהה {hy:.1f}%: גבוה", "hy_elevated", v=round(hy, 1))
    if hy is not None and hy_prev is not None and hy - hy_prev >= 1.0:
        add("stress", 1, f"Credit spreads widened {hy - hy_prev:.1f} points in a month",
            f"מרווחי האשראי התרחבו ב-{hy - hy_prev:.1f} נקודות בחודש", "hy_widening", v=round(hy - hy_prev, 1))

    fsi = i.get("STLFSI4")
    if fsi is not None and fsi >= 1.5:
        add("stress", 2, f"Financial stress index at {fsi:.2f}: high", f"מדד הלחץ הפיננסי {fsi:.2f}: גבוה", "fsi_high", v=round(fsi, 2))
    elif fsi is not None and fsi > 0:
        add("stress", 1, f"Financial stress index at {fsi:.2f}: above normal",
            f"מדד הלחץ הפיננסי {fsi:.2f}: מעל הרגיל", "fsi_above", v=round(fsi, 2))

    nfci = i.get("NFCI")
    if nfci is not None and nfci > 0:
        add("stress", 1, f"Financial conditions tighter than average (NFCI {nfci:.2f})",
            f"התנאים הפיננסיים הדוקים מהממוצע (NFCI {nfci:.2f})", "nfci_tight", v=round(nfci, 2))

    curve, curve_min = i.get("T10Y2Y"), i.get("t10y2y_min_1y")
    if curve is not None and curve < 0:
        add("stress", 1, f"Yield curve inverted (10Y-2Y {curve:.2f})",
            f"עקום התשואות הפוך (10Y-2Y {curve:.2f})", "curve_inverted", v=round(curve, 2))
    elif curve is not None and curve_min is not None and curve_min <= -0.25:
        add("stress", 1, "Yield curve has just come out of an inversion, which has preceded past recessions",
            "עקום התשואות יצא לאחרונה מהיפוך, מצב שקדם למיתונים בעבר", "curve_uninverted")

    b = i.get("breadth_pct")
    if b is not None and b < 25:
        add("breadth", 2, f"Only {b:.0f}% of analysed stocks are above their 200-day average",
            f"רק {b:.0f}% מהמניות המנותחות מעל ממוצע 200 הימים", "breadth_low", pct=round(b))
    elif b is not None and b < 40:
        add("breadth", 1, f"{b:.0f}% of analysed stocks are above their 200-day average",
            f"{b:.0f}% מהמניות המנותחות מעל ממוצע 200 הימים", "breadth_weak", pct=round(b))

    # ── Global ──
    REGION_HE = {"europe": "אירופה", "japan": "יפן", "china": "סין", "emerging": "שווקים מתעוררים"}
    weak = [r for r in REGION_ETFS if i.get(f"{r}_vs200") is not None and i[f"{r}_vs200"] < 0]
    known_regions = [r for r in REGION_ETFS if i.get(f"{r}_vs200") is not None]
    if len(weak) >= 3:
        add("global", 2, f"{len(weak)} of {len(known_regions)} world regions are below their 200-day average",
            f"{len(weak)} מתוך {len(known_regions)} אזורים בעולם מתחת לממוצע 200 הימים",
            "global_broad_weak", n=len(weak), total=len(known_regions))
    elif len(weak) == 2:
        add("global", 1, f"2 of {len(known_regions)} world regions are below their 200-day average",
            f"2 מתוך {len(known_regions)} אזורים בעולם מתחת לממוצע 200 הימים",
            "global_weak", n=2, total=len(known_regions))
    for r in REGION_ETFS:
        d = i.get(f"{r}_drawdown")
        if d is not None and d >= 20:
            add("global", 1, f"{r} is {d}% below its one-year high (bear market)",
                f"{REGION_HE[r]} נמוך ב-{d}% מהשיא השנתי (שוק דובי)", "region_bear", region=r, pct=d)
    sc = i.get("smallcaps_vs200")
    if sc is not None and sc < 0:
        add("global", 1, "US small caps are below their 200-day average",
            "המניות הקטנות בארה״ב מתחת לממוצע 200 הימים", "smallcaps_below_200")
    eu = i.get("BAMLHE00EHYIOAS")
    if eu is not None and eu >= 7:
        add("global", 2, f"European high-yield spread at {eu:.1f}%: credit stress",
            f"מרווח אשראי בתשואה גבוהה באירופה {eu:.1f}%: לחץ אשראי", "eu_hy_stress", v=round(eu, 1))
    elif eu is not None and eu >= 5:
        add("global", 1, f"European high-yield spread at {eu:.1f}%: elevated",
            f"מרווח אשראי בתשואה גבוהה באירופה {eu:.1f}%: גבוה", "eu_hy_elevated", v=round(eu, 1))
    usd = i.get("dollar_1m_pct")
    if usd is not None and usd >= 3:
        add("global", 1, f"The dollar rose {usd:.1f}% in a month: money running for safety",
            f"הדולר עלה {usd:.1f}% בחודש: כסף בורח למקום בטוח", "dollar_surge", v=round(usd, 1))
    yen = i.get("yen_1m_pct")
    if yen is not None and yen >= 5:
        add("global", 1, f"The yen rose {yen:.1f}% in a month: carry trades unwinding",
            f"הין עלה {yen:.1f}% בחודש: פירוק עסקאות מימון בין", "yen_surge", v=round(yen, 1))

    score = trend + stress + breadth + global_
    # The yield curve is a slow, macro signal: an un-inversion can stand for a
    # year. It counts toward the score, but not toward the override, which is
    # for the fast stress measures flashing together.
    curve_pts = sum(x["points"] for x in reasons if x.get("code", "").startswith("curve_"))
    if score >= STRESS_AT or stress - curve_pts >= STRESS_LAYER_OVERRIDE:
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
        "layers": {"trend": trend, "stress": stress, "breadth": breadth, "global": global_},
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


# ─── Market screen ────────────────────────────────────────────────────────────

def indicator_table(i: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every measure the reading uses, with its value, the thresholds that
    count against the market, and a status — so the screen can show exactly
    what was checked, not only the verdict. `status`: ok / warn / alert /
    unknown. Thresholds match assess()."""
    def row(key, layer, value, warn, alert, higher_is_worse=True, fmt=None):
        if value is None:
            status = "unknown"
        else:
            bad = (lambda t: value >= t) if higher_is_worse else (lambda t: value <= t)
            status = "alert" if alert is not None and bad(alert) else "warn" if warn is not None and bad(warn) else "ok"
        return {"key": key, "layer": layer, "value": value, "warn_at": warn, "alert_at": alert,
                "higher_is_worse": higher_is_worse, "status": status}

    spy, ma50, ma200, high = i.get("spy"), i.get("spy_ma50"), i.get("spy_ma200"), i.get("spy_high_1y")
    vs200 = round((spy - ma200) / ma200 * 100, 1) if spy and ma200 else None
    vs50 = round((spy - ma50) / ma50 * 100, 1) if spy and ma50 else None
    dd = round((high - spy) / high * 100, 1) if spy and high else None
    hy, hy_prev = i.get("BAMLH0A0HYM2"), i.get("hy_spread_1m_ago")
    widen = round(hy - hy_prev, 2) if hy is not None and hy_prev is not None else None
    curve = i.get("T10Y2Y")
    rows = [
        row("spy_vs_200", "trend", vs200, 0.0, None, higher_is_worse=False),
        row("spy_vs_50", "trend", vs50, 0.0, None, higher_is_worse=False),
        row("drawdown", "trend", dd, 10, 20),
        row("vix", "stress", i.get("VIXCLS"), 25, 35),
        row("hy_spread", "stress", hy, 5, 7),
        row("hy_widening_1m", "stress", widen, 1.0, None),
        row("stlfsi", "stress", i.get("STLFSI4"), 0.0001, 1.5),
        row("nfci", "stress", i.get("NFCI"), 0.0001, None),
        row("yield_curve", "stress", curve, 0.0, None, higher_is_worse=False),
        row("breadth", "breadth", i.get("breadth_pct"), 40, 25, higher_is_worse=False),
    ]
    for region in list(REGION_ETFS) + ["smallcaps"]:
        v, d = i.get(f"{region}_vs200"), i.get(f"{region}_drawdown")
        status = ("unknown" if v is None else
                  "alert" if d is not None and d >= 20 else "warn" if v < 0 else "ok")
        rows.append({"key": f"region_{region}", "layer": "global", "value": v, "drawdown": d,
                     "warn_at": 0.0, "alert_at": None, "higher_is_worse": False, "status": status})
    rows += [
        row("eu_hy_spread", "global", i.get("BAMLHE00EHYIOAS"), 5, 7),
        row("dollar_1m", "global", round(i["dollar_1m_pct"], 2) if i.get("dollar_1m_pct") is not None else None, 3, None),
        row("yen_1m", "global", round(i["yen_1m_pct"], 2) if i.get("yen_1m_pct") is not None else None, 5, None),
    ]
    # A positive curve that only just stopped being inverted still warns.
    for r_ in rows:
        if r_["key"] == "yield_curve" and curve is not None and curve >= 0 \
                and (i.get("t10y2y_min_1y") or 0) <= -0.25:
            r_["status"] = "warn"
            r_["note"] = "uninverted"
        if r_["key"] in ("spy_vs_200", "spy_vs_50") and r_["value"] is not None:
            r_["status"] = "warn" if r_["value"] < 0 else "ok"
        if r_["key"] == "yield_curve" and curve is not None and curve < 0:
            r_["status"] = "warn"
        if r_["key"] == "breadth" and r_["value"] is not None:
            v = r_["value"]
            r_["status"] = "alert" if v < 25 else "warn" if v < 40 else "ok"
    return rows


async def fred_series_1y(redis_client, series_id: str) -> List[List[Any]]:
    """[[date, value], ...] for the past year, cached for six hours."""
    import json
    key = f"investment_ai:fred_series:{series_id}"
    try:
        raw = await redis_client.get(key)
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    async with httpx.AsyncClient() as client:
        hist = await _fred_history(client, series_id)
    out = [[d, v] for d, v in hist[-260:]]
    if out:
        try:
            await redis_client.set(key, json.dumps(out), ex=6 * 3600)
        except Exception:
            pass
    return out


def with_reason_codes(reading: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """A stored reading whose reasons predate reason codes (and so show in
    English for every language) gets them by re-scoring its own inputs.
    The regime itself is left exactly as it was committed."""
    if not reading or not reading.get("inputs"):
        return reading
    if all(r.get("code") for r in reading.get("reasons", [])):
        return reading
    fresh = assess(reading["inputs"])
    return {**reading, "reasons": fresh["reasons"]}


async def refresh_outdated_reading(redis_client) -> Optional[str]:
    """Bring a reading made by older code up to date now, rather than at the
    next close: a reading without the global layer shows that whole section
    as "no data" for a day.

    Never changes the regime users were told about. Same regime: the details
    are replaced (keeping the date it began). Different regime: stored only
    as the latest reading, for the normal two-reading confirmation to decide.
    """
    import json
    committed = await current(redis_client)
    if not committed or "global" in (committed.get("layers") or {}):
        return None
    inputs = await fetch_inputs()
    reading = assess(inputs)
    if reading["inputs_available"] < 4:
        return "too few inputs"
    await redis_client.set(REDIS_KEY + ":latest", json.dumps(reading), ex=14 * 24 * 3600)
    if reading["regime"] != committed.get("regime"):
        return f"latest only ({reading['regime']} vs committed {committed.get('regime')})"
    reading["since"] = committed.get("since") or committed.get("as_of")
    await redis_client.set(REDIS_KEY, json.dumps(reading))
    return "refreshed"
