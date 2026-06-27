"""
Pre-Screener — ranks ~900 universe stocks and selects TOP_N for full Claude analysis.

Scoring model (0–100, percentile-based so we always get exactly TOP_N):

  Weight  Metric
  ──────  ──────────────────────────────────────────────
  30 %    EPS growth (QoQ — most recent quarter vs year-ago quarter)
  25 %    Revenue growth (YoY — trailing 12 months)
  20 %    Relative valuation (P/E vs sector median — lower = better)
  15 %    Price momentum (3-month total return)
  10 %    Financial health (low Debt/Equity + positive FCF)

Steps:
  1. Load all in_universe assets from DB (~900 stocks)
  2. Fetch lightweight financial data via yfinance (no Claude = zero cost)
  3. Hard-filter: remove penny stocks, illiquid, missing data
  4. Score each metric as a percentile rank within the surviving universe
  5. Compute weighted composite score
  6. Mark top TOP_N as is_active_in_pool = True, rest = False
  7. Assign direction_bias: LONG for top 80, SHORT for ranks 81-100
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import yfinance as yf

logger = logging.getLogger(__name__)

TOP_N               = 100
LONG_COUNT          = 80
MIN_PRICE           = 1.0
MIN_MARKET_CAP      = 500_000_000
MIN_AVG_VOLUME      = 100_000
MAX_DEBT_EQUITY     = 5.0
MAX_PE_RATIO        = 200.0
FETCH_BATCH_SIZE    = 5
SLEEP_BETWEEN_BATCHES = 2.0
W_EPS_GROWTH    = 0.30
W_REV_GROWTH    = 0.25
W_VALUATION     = 0.20
W_MOMENTUM      = 0.15
W_HEALTH        = 0.10


@dataclass
class StockMetrics:
    symbol:       str
    sector:       Optional[str]   = None
    price:        Optional[float] = None
    market_cap:   Optional[float] = None
    avg_volume:   Optional[float] = None
    pe_ratio:     Optional[float] = None
    eps_growth:   Optional[float] = None
    rev_growth:   Optional[float] = None
    momentum_3m:  Optional[float] = None
    debt_equity:  Optional[float] = None
    fcf:          Optional[float] = None
    score_eps:        float = 0.0
    score_rev:        float = 0.0
    score_valuation:  float = 0.0
    score_momentum:   float = 0.0
    score_health:     float = 0.0
    composite_score:  float = 0.0
    passes_hard_filter: bool = False


async def _fetch_metrics(symbol: str) -> StockMetrics:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_metrics_sync, symbol)


def _fetch_metrics_sync(symbol: str) -> StockMetrics:
    import time
    m = StockMetrics(symbol=symbol)
    for attempt in range(3):
        try:
            tk = yf.Ticker(symbol)
            info = tk.info or {}
            m.sector      = info.get("sector")
            m.price       = info.get("currentPrice") or info.get("regularMarketPrice")
            m.market_cap  = info.get("marketCap")
            m.avg_volume  = info.get("averageDailyVolume10Day") or info.get("averageVolume")
            m.pe_ratio    = info.get("trailingPE") or info.get("forwardPE")
            m.debt_equity = info.get("debtToEquity")
            if m.debt_equity and m.debt_equity > 20:
                m.debt_equity = m.debt_equity / 100
            try:
                cf = tk.cashflow
                if cf is not None and not cf.empty and "Free Cash Flow" in cf.index:
                    m.fcf = float(cf.loc["Free Cash Flow"].iloc[0])
            except Exception:
                pass
            try:
                qe = tk.quarterly_earnings
                if qe is not None and len(qe) >= 5:
                    eps_recent   = float(qe["Earnings"].iloc[0])
                    eps_year_ago = float(qe["Earnings"].iloc[4])
                    if eps_year_ago and eps_year_ago != 0:
                        m.eps_growth = (eps_recent - eps_year_ago) / abs(eps_year_ago) * 100
            except Exception:
                pass
            rev = info.get("revenueGrowth")
            if rev is not None:
                m.rev_growth = rev * 100
            try:
                hist = tk.history(period="3mo", interval="1d")
                if hist is not None and len(hist) >= 20:
                    sp = float(hist["Close"].iloc[0])
                    ep = float(hist["Close"].iloc[-1])
                    if sp and sp > 0:
                        m.momentum_3m = (ep - sp) / sp * 100
            except Exception:
                pass
            return m
        except Exception as e:
            if "429" in str(e) and attempt < 2:
                wait = 15 * (attempt + 1)
                logger.debug(f"[pre_screener] {symbol}: rate limited, retry in {wait}s")
                time.sleep(wait)
            else:
                logger.debug(f"[pre_screener] {symbol}: {e}")
                return m
    return m


def _apply_hard_filter(m: StockMetrics) -> bool:
    if not m.price      or m.price      < MIN_PRICE:       return False
    if not m.market_cap or m.market_cap < MIN_MARKET_CAP:  return False
    if not m.avg_volume or m.avg_volume < MIN_AVG_VOLUME:  return False
    if m.pe_ratio    and m.pe_ratio    > MAX_PE_RATIO:     return False
    if m.debt_equity and m.debt_equity > MAX_DEBT_EQUITY:  return False
    return sum([m.eps_growth is not None, m.rev_growth is not None, m.momentum_3m is not None]) >= 1


def _pct(values, val):
    if val is None: return 0.0
    clean = [v for v in values if v is not None]
    if not clean: return 50.0
    return round(sum(1 for v in clean if v < val) / len(clean) * 100, 1)


def _pct_inv(values, val):
    if val is None: return 50.0
    clean = [v for v in values if v is not None]
    if not clean: return 50.0
    return round(sum(1 for v in clean if v > val) / len(clean) * 100, 1)


def _score_all(stocks):
    universe = [s for s in stocks if s.passes_hard_filter]
    eps_vals = [s.eps_growth  for s in universe]
    rev_vals = [s.rev_growth  for s in universe]
    mom_vals = [s.momentum_3m for s in universe]
    sector_pe = {}
    for s in universe:
        if s.sector and s.pe_ratio and s.pe_ratio > 0:
            sector_pe.setdefault(s.sector, []).append(s.pe_ratio)
    sector_med = {sec: sorted(v)[len(v)//2] for sec, v in sector_pe.items()}
    rel_pe = [(s.pe_ratio/sector_med[s.sector]) if (s.pe_ratio and s.sector and s.sector in sector_med) else None for s in universe]
    def health(s):
        if s.debt_equity is None and s.fcf is None: return None
        return (1/(1+(s.debt_equity or 0)))*50 + (50.0 if (s.fcf or 0)>0 else 0.0)
    health_vals = [health(s) for s in universe]
    for i, s in enumerate(universe):
        s.score_eps       = _pct(eps_vals, s.eps_growth)
        s.score_rev       = _pct(rev_vals, s.rev_growth)
        s.score_momentum  = _pct(mom_vals, s.momentum_3m)
        s.score_valuation = _pct_inv(rel_pe, rel_pe[i])
        s.score_health    = _pct(health_vals, health_vals[i])
        s.composite_score = round(
            s.score_eps*W_EPS_GROWTH + s.score_rev*W_REV_GROWTH +
            s.score_valuation*W_VALUATION + s.score_momentum*W_MOMENTUM +
            s.score_health*W_HEALTH, 2)


async def _update_db(db, ranked, all_symbols):
    from app.db.models.asset import Asset
    from sqlalchemy import update
    long_syms  = {s.symbol for s in ranked[:LONG_COUNT]}
    short_syms = {s.symbol for s in ranked[LONG_COUNT:TOP_N]}
    await db.execute(update(Asset).where(Asset.symbol.in_(all_symbols)).values(is_active_in_pool=False))
    if long_syms:
        await db.execute(update(Asset).where(Asset.symbol.in_(long_syms)).values(is_active_in_pool=True, direction_bias="LONG"))
    if short_syms:
        await db.execute(update(Asset).where(Asset.symbol.in_(short_syms)).values(is_active_in_pool=True, direction_bias="SHORT"))
    for s in ranked[:TOP_N]:
        await db.execute(update(Asset).where(Asset.symbol==s.symbol).values(fundamental_score=s.composite_score))


async def run_pre_screener(db) -> dict:
    """Rank universe stocks by financial score and activate top 100. db is an open AsyncSession."""
    from app.db.models.asset import Asset
    from sqlalchemy import select
    logger.info("[pre_screener] starting")
    rows = await db.execute(select(Asset.symbol).where(Asset.in_universe == True))
    all_symbols = [r[0] for r in rows.all()]
    if not all_symbols:
        return {"universe_size": 0, "passed_filter": 0, "selected": 0, "long": 0, "short": 0, "rejected": 0, "errors": 0}
    logger.info(f"[pre_screener] {len(all_symbols)} stocks — fetching data…")
    metrics = []
    errors = 0
    for i in range(0, len(all_symbols), FETCH_BATCH_SIZE):
        batch = all_symbols[i:i+FETCH_BATCH_SIZE]
        results = await asyncio.gather(*[_fetch_metrics(sym) for sym in batch], return_exceptions=True)
        for sym, res in zip(batch, results):
            if isinstance(res, Exception):
                errors += 1
                metrics.append(StockMetrics(symbol=sym))
            else:
                metrics.append(res)
        await asyncio.sleep(SLEEP_BETWEEN_BATCHES)
    for m in metrics:
        m.passes_hard_filter = _apply_hard_filter(m)
    passed = [m for m in metrics if m.passes_hard_filter]
    logger.info(f"[pre_screener] {len(passed)}/{len(metrics)} passed filters")
    _score_all(metrics)
    ranked = sorted(passed, key=lambda m: m.composite_score, reverse=True)
    top = ranked[:TOP_N]
    if top:
        logger.info(f"[pre_screener] top {len(top)} | score {top[-1].composite_score:.1f}–{top[0].composite_score:.1f}")
    await _update_db(db, ranked, all_symbols)
    return {
        "universe_size": len(all_symbols),
        "passed_filter": len(passed),
        "selected":      len(top),
        "long":          min(len(top), LONG_COUNT),
        "short":         max(0, len(top)-LONG_COUNT),
        "rejected":      len(all_symbols)-len(top),
        "errors":        errors,
    }
