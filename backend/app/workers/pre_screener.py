"""
Pre-Screener — ranks ~900 universe stocks and selects TOP_N for full Claude analysis.

Uses only yf.download() (bulk price/volume download) — avoids per-symbol
Yahoo Finance API calls that get rate-limited from Railway IPs.

Scoring model (percentile-based):
  50%  3-month price momentum
  30%  6-month price momentum
  20%  volume trend (recent 20-day avg vs 60-day avg)

Top 80 → LONG, ranks 81-100 → SHORT (highest negative momentum)
Claude then does full fundamental analysis in the daily full_scan.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)

TOP_N      = 100
LONG_COUNT = 80
MIN_PRICE  = 1.0
MIN_AVG_VOLUME = 100_000
MIN_AVG_VOLUME_TASE = 10_000   # TASE shares often have lower daily volume counts
DOWNLOAD_CHUNK = 200   # symbols per yf.download() call


@dataclass
class StockMetrics:
    symbol:      str
    price:       Optional[float] = None
    avg_volume:  Optional[float] = None
    momentum_3m: Optional[float] = None
    momentum_6m: Optional[float] = None
    vol_trend:   Optional[float] = None   # recent_vol / older_vol ratio
    score:       float = 0.0
    passes_filter: bool = False


def _download_chunk(symbols: List[str], period: str = "6mo") -> Dict[str, pd.DataFrame]:
    """Download OHLCV for a chunk of symbols. Returns {symbol: df}."""
    import time
    for attempt in range(3):
        try:
            data = yf.download(
                symbols, period=period, interval="1d",
                group_by="ticker", auto_adjust=True,
                progress=False, threads=False,
            )
            result = {}
            for sym in symbols:
                try:
                    if len(symbols) == 1:
                        df = data
                    else:
                        df = data[sym]
                    df = df.dropna(subset=["Close"])
                    if len(df) >= 20:
                        result[sym] = df
                except Exception:
                    pass
            return result
        except Exception as e:
            if attempt < 2:
                time.sleep(10 * (attempt + 1))
            else:
                logger.warning(f"[pre_screener] download chunk failed: {e}")
    return {}


def _compute_metrics(symbol: str, df: pd.DataFrame) -> StockMetrics:
    m = StockMetrics(symbol=symbol)
    closes = df["Close"]
    volumes = df["Volume"] if "Volume" in df.columns else None

    m.price = float(closes.iloc[-1])

    # 3-month momentum (~63 trading days)
    idx_3m = max(0, len(closes) - 63)
    if len(closes) > idx_3m:
        start = float(closes.iloc[idx_3m])
        if start > 0:
            m.momentum_3m = (m.price - start) / start * 100

    # 6-month momentum (full period)
    if len(closes) >= 20:
        start6 = float(closes.iloc[0])
        if start6 > 0:
            m.momentum_6m = (m.price - start6) / start6 * 100

    # Volume trend: last 20 days vs previous 40 days
    if volumes is not None and len(volumes) >= 60:
        recent = float(volumes.iloc[-20:].mean())
        older  = float(volumes.iloc[-60:-20].mean())
        m.avg_volume = recent
        if older > 0:
            m.vol_trend = recent / older
    elif volumes is not None and len(volumes) >= 20:
        m.avg_volume = float(volumes.iloc[-20:].mean())

    return m


def _pct(values, val):
    if val is None:
        return 0.0
    clean = [v for v in values if v is not None]
    if not clean:
        return 50.0
    return round(sum(1 for v in clean if v < val) / len(clean) * 100, 1)


def _score_all(stocks: List[StockMetrics]) -> None:
    universe = [s for s in stocks if s.passes_filter]
    mom3  = [s.momentum_3m for s in universe]
    mom6  = [s.momentum_6m for s in universe]
    vtrnd = [s.vol_trend   for s in universe]
    for s in universe:
        p3 = _pct(mom3,  s.momentum_3m)
        p6 = _pct(mom6,  s.momentum_6m)
        pv = _pct(vtrnd, s.vol_trend)
        s.score = round(p3 * 0.50 + p6 * 0.30 + pv * 0.20, 2)


async def _update_db(db, ranked: List[StockMetrics], all_symbols: List[str]) -> None:
    from app.db.models.asset import Asset, DirectionBias
    from sqlalchemy import update
    long_syms  = {s.symbol for s in ranked[:LONG_COUNT]}
    short_syms = {s.symbol for s in ranked[LONG_COUNT:TOP_N]}
    await db.execute(
        update(Asset).where(Asset.symbol.in_(all_symbols)).values(is_active_in_pool=False)
    )
    if long_syms:
        await db.execute(
            update(Asset).where(Asset.symbol.in_(long_syms))
            .values(is_active_in_pool=True, direction_bias=DirectionBias.LONG)
        )
    if short_syms:
        await db.execute(
            update(Asset).where(Asset.symbol.in_(short_syms))
            .values(is_active_in_pool=True, direction_bias=DirectionBias.SHORT)
        )
    for s in ranked[:TOP_N]:
        await db.execute(
            update(Asset).where(Asset.symbol == s.symbol)
            .values(fundamental_score=s.score)
        )


async def run_pre_screener(db) -> dict:
    """Rank universe stocks by momentum score and activate top 100."""
    from app.db.models.asset import Asset
    from sqlalchemy import select

    logger.info("[pre_screener] starting")
    rows = await db.execute(select(Asset.symbol).where(Asset.in_universe == True))
    all_symbols = [r[0] for r in rows.all()]
    # Release the read transaction before the long download phase — otherwise the
    # session sits idle-in-transaction for minutes and managed Postgres
    # (idle_in_transaction_session_timeout) may kill it mid-run.
    await db.commit()
    if not all_symbols:
        return {"universe_size": 0, "passed_filter": 0, "selected": 0, "long": 0, "short": 0}

    logger.info(f"[pre_screener] {len(all_symbols)} symbols — downloading price data")
    loop = asyncio.get_event_loop()
    all_data: Dict[str, pd.DataFrame] = {}

    for i in range(0, len(all_symbols), DOWNLOAD_CHUNK):
        chunk = all_symbols[i: i + DOWNLOAD_CHUNK]
        chunk_data = await loop.run_in_executor(None, _download_chunk, chunk)
        all_data.update(chunk_data)
        logger.info(f"[pre_screener] downloaded {min(i+DOWNLOAD_CHUNK, len(all_symbols))}/{len(all_symbols)}")
        await asyncio.sleep(3)

    logger.info(f"[pre_screener] {len(all_data)}/{len(all_symbols)} symbols have data — computing metrics")
    metrics = []
    for sym in all_symbols:
        if sym in all_data:
            m = _compute_metrics(sym, all_data[sym])
            min_vol = MIN_AVG_VOLUME_TASE if sym.endswith(".TA") else MIN_AVG_VOLUME
            m.passes_filter = (
                m.price is not None and m.price >= MIN_PRICE and
                m.avg_volume is not None and m.avg_volume >= min_vol and
                m.momentum_3m is not None
            )
        else:
            m = StockMetrics(symbol=sym)
        metrics.append(m)

    passed = [m for m in metrics if m.passes_filter]
    logger.info(f"[pre_screener] {len(passed)}/{len(metrics)} passed filters")

    # Fallback when fewer than TOP_N pass the volume/price filters.
    # Rescue only symbols that actually returned price data — a symbol with no
    # data (delisted or bogus ticker) must never be activated into the pool,
    # where it would burn a full Claude analysis in the weekly scan.
    if len(passed) < TOP_N:
        existing = {m.symbol for m in passed}
        rescued = [m for m in metrics if m.symbol not in existing and m.price is not None]
        for m in rescued:
            m.passes_filter = True
        passed = passed + rescued
        logger.warning(
            f"[pre_screener] only {len(existing)} passed filters — rescued {len(rescued)} "
            f"symbols with price data (total {len(passed)})"
        )
        if not passed:
            # Yahoo fully blocked: keep the system alive with arbitrary symbols;
            # Claude does the real analysis in full_scan.
            logger.warning("[pre_screener] no price data at all — falling back to arbitrary symbols")
            fallback = [StockMetrics(symbol=s, passes_filter=True, score=0.0) for s in all_symbols]
            import random
            random.shuffle(fallback)
            passed = fallback[:TOP_N]

    _score_all(metrics)
    ranked = sorted(passed, key=lambda m: m.score, reverse=True)
    top = ranked[:TOP_N]

    if top:
        logger.info(f"[pre_screener] top {len(top)} | score range {top[-1].score:.1f}–{top[0].score:.1f}")

    await _update_db(db, ranked, all_symbols)
    await db.commit()

    return {
        "universe_size":  len(all_symbols),
        "data_fetched":   len(all_data),
        "passed_filter":  len(passed),
        "selected":       len(top),
        "long":           min(len(top), LONG_COUNT),
        "short":          max(0, len(top) - LONG_COUNT),
    }
