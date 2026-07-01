"""
Universe Loader
Fetches S&P 500 + S&P 400 constituent lists from Wikipedia and the TA-125 curated
list and seeds them into the assets table with in_universe=True, is_active_in_pool=False.
Run as a Celery task (weekly) or call load_universe() directly.
"""
import asyncio
import logging
from typing import Optional

import pandas as pd
import requests as _requests
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.db.models.asset import Asset, Exchange, AssetType, RiskLevel
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Wikipedia URLs for index constituents
_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
_SP400_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"

_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; InvestmentAI/1.0; research bot)",
}

# TA-125 (Tel Aviv Stock Exchange) — major Israeli index constituents.
# Using Yahoo Finance .TA suffix format so the pre-screener's yf.download() works.
# symbol, name, name_hebrew, sector, risk_level, cap_tier
_TA125_STOCKS: list[tuple] = [
    # ── Banks ────────────────────────────────────────────────────────────────
    ("LUMI.TA",  "Bank Leumi",                "בנק לאומי",             "Financial",          RiskLevel.LOW,    "LARGE"),
    ("POLI.TA",  "Bank Hapoalim",             "בנק הפועלים",           "Financial",          RiskLevel.LOW,    "LARGE"),
    ("DSCT.TA",  "Discount Bank",             "בנק דיסקונט",           "Financial",          RiskLevel.LOW,    "LARGE"),
    ("MIZR.TA",  "Mizrahi-Tefahot Bank",      "מזרחי טפחות",           "Financial",          RiskLevel.LOW,    "LARGE"),
    ("FTIN.TA",  "First International Bank",  "הבנק הבינלאומי",        "Financial",          RiskLevel.LOW,    "MID"),
    # ── Insurance ────────────────────────────────────────────────────────────
    ("PHOE.TA",  "Phoenix Holdings",          "פניקס",                 "Financial",          RiskLevel.MEDIUM, "LARGE"),
    ("CLLT.TA",  "Clal Insurance",            "כלל ביטוח",             "Financial",          RiskLevel.MEDIUM, "MID"),
    ("MGDL.TA",  "Migdal Insurance",          "מגדל",                  "Financial",          RiskLevel.MEDIUM, "MID"),
    ("MMHD.TA",  "Menorah Mivtachim",         "מנורה מבטחים",          "Financial",          RiskLevel.MEDIUM, "MID"),
    # ── Technology / Cyber / Defense ─────────────────────────────────────────
    ("NICE.TA",  "Nice Systems",              "נייס",                  "Technology",         RiskLevel.MEDIUM, "LARGE"),
    ("CHKP.TA",  "Check Point Software",      "צ'ק פוינט",             "Technology",         RiskLevel.LOW,    "LARGE"),
    ("WIX.TA",   "Wix.com",                   "וויקס",                 "Technology",         RiskLevel.HIGH,   "LARGE"),
    ("ESLT.TA",  "Elbit Systems",             "אלביט מערכות",          "Industrials",        RiskLevel.MEDIUM, "LARGE"),
    ("TSEM.TA",  "Tower Semiconductor",       "טאואר סמיקונדקטור",     "Technology",         RiskLevel.HIGH,   "MID"),
    # ── Telecom ──────────────────────────────────────────────────────────────
    ("BEZQ.TA",  "Bezeq",                     "בזק",                   "Communication",      RiskLevel.LOW,    "LARGE"),
    ("PTNR.TA",  "Partner Communications",    "פרטנר",                 "Communication",      RiskLevel.MEDIUM, "MID"),
    ("CLBH.TA",  "Cellcom Israel",            "סלקום",                 "Communication",      RiskLevel.MEDIUM, "MID"),
    # ── Chemicals / Materials ─────────────────────────────────────────────────
    ("ICL.TA",   "ICL Group",                 "כיל",                   "Basic Materials",    RiskLevel.MEDIUM, "LARGE"),
    # ── Energy ───────────────────────────────────────────────────────────────
    ("DLEKG.TA", "Delek Group",               "דלק קבוצה",             "Energy",             RiskLevel.HIGH,   "MID"),
    ("ENLT.TA",  "Enlight Renewable Energy",  "אנלייט",                "Energy",             RiskLevel.MEDIUM, "MID"),
    # ── Healthcare / Pharma ──────────────────────────────────────────────────
    ("TEVA.TA",  "Teva Pharmaceutical",       "טבע",                   "Healthcare",         RiskLevel.MEDIUM, "LARGE"),
    # ── Real Estate ──────────────────────────────────────────────────────────
    ("AZRT.TA",  "Azrieli Group",             "אזריאלי",               "Real Estate",        RiskLevel.LOW,    "LARGE"),
    ("AMOT.TA",  "Amot Investments",          "אמות",                  "Real Estate",        RiskLevel.LOW,    "MID"),
    ("SPEN.TA",  "Shapir Engineering",        "שפיר",                  "Industrials",        RiskLevel.MEDIUM, "MID"),
    # ── Retail / Consumer ────────────────────────────────────────────────────
    ("RTLS.TA",  "Rami Levy Hashikma",        "רמי לוי",               "Consumer Defensive", RiskLevel.MEDIUM, "MID"),
    ("SANO.TA",  "Sano Consumer Products",    "סנו",                   "Consumer Defensive", RiskLevel.LOW,    "MID"),
    # ── Industrial / Conglomerates ────────────────────────────────────────────
    ("ELCO.TA",  "Elco Holdings",             "אלקו",                  "Industrials",        RiskLevel.MEDIUM, "MID"),
    # ── Additional TA-125 blue chips ─────────────────────────────────────────
    ("ILCO.TA",  "Israel Corporation",        "קורפ ישראל",            "Industrials",        RiskLevel.MEDIUM, "LARGE"),
    ("MMAN.TA",  "Maman Cargo Airports",      "מאמן",                  "Industrials",        RiskLevel.LOW,    "MID"),
    ("ALHE.TA",  "Alony-Hetz Properties",     "אלוני חץ",              "Real Estate",        RiskLevel.LOW,    "MID"),
]


def _fetch_sp500() -> list[dict]:
    """Fetch S&P 500 constituents from Wikipedia (synchronous — run in thread)."""
    try:
        resp = _requests.get(_SP500_URL, headers=_HTTP_HEADERS, timeout=30)
        resp.raise_for_status()
        tables = pd.read_html(resp.text)
        df = tables[0]
        results = []
        for _, row in df.iterrows():
            symbol = str(row.get("Symbol", "")).strip().replace(".", "-")
            name = str(row.get("Security", "")).strip()
            sector = str(row.get("GICS Sector", "")).strip()
            if symbol and name and symbol != "nan":
                results.append({
                    "symbol": symbol,
                    "name": name,
                    "sector": sector or "Other",
                    "cap_tier": "LARGE",
                })
        logger.info(f"Fetched {len(results)} S&P 500 constituents")
        return results
    except Exception as e:
        logger.error(f"Failed to fetch S&P 500: {e}")
        return []


def _fetch_sp400() -> list[dict]:
    """Fetch S&P 400 (Mid Cap) constituents from Wikipedia (synchronous — run in thread)."""
    try:
        resp = _requests.get(_SP400_URL, headers=_HTTP_HEADERS, timeout=30)
        resp.raise_for_status()
        tables = pd.read_html(resp.text)
        df = tables[0]
        results = []
        for _, row in df.iterrows():
            symbol = str(row.get("Ticker symbol", row.get("Symbol", row.get("Ticker", "")))).strip().replace(".", "-")
            name = str(row.get("Company", row.get("Security", row.get("Name", "")))).strip()
            sector = str(row.get("GICS Sector", row.get("Sector", ""))).strip()
            if symbol and name and symbol != "nan":
                results.append({
                    "symbol": symbol,
                    "name": name,
                    "sector": sector or "Other",
                    "cap_tier": "MID",
                })
        logger.info(f"Fetched {len(results)} S&P 400 constituents")
        return results
    except Exception as e:
        logger.error(f"Failed to fetch S&P 400: {e}")
        return []


def _infer_exchange(symbol: str) -> Exchange:
    """Best-effort exchange assignment; yfinance handles both anyway."""
    nasdaq_hints = {"AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "GOOG", "AVGO", "COST"}
    if symbol in nasdaq_hints:
        return Exchange.NASDAQ
    return Exchange.NYSE


async def load_universe(db: AsyncSession) -> dict:
    """
    Load S&P 500 + S&P 400 + TA-125 into universe.
    New symbols are inserted; existing symbols get in_universe=True updated.
    Runs Wikipedia fetches in thread pool to avoid blocking the async event loop.
    Returns {inserted, updated, skipped, tase_added}.
    """
    # Run blocking HTTP+pandas calls in thread pool so the event loop stays free
    stocks_500, stocks_400 = await asyncio.gather(
        asyncio.to_thread(_fetch_sp500),
        asyncio.to_thread(_fetch_sp400),
    )
    us_stocks = stocks_500 + stocks_400
    logger.info(f"[universe] S&P 500+400: {len(us_stocks)} stocks")

    # Load all existing symbols once
    existing_result = await db.execute(select(Asset.symbol, Asset.in_universe))
    existing = {row[0]: row[1] for row in existing_result.fetchall()}

    inserted = 0
    updated = 0
    new_assets = []
    all_symbols: set[str] = set()

    # ── US stocks ────────────────────────────────────────────────────────────
    for stock in us_stocks:
        symbol = stock["symbol"]
        all_symbols.add(symbol)

        if symbol in existing:
            if not existing[symbol]:
                await db.execute(update(Asset).where(Asset.symbol == symbol).values(in_universe=True))
                updated += 1
        else:
            new_assets.append(Asset(
                symbol=symbol,
                name=stock["name"],
                exchange=_infer_exchange(symbol),
                asset_type=AssetType.STOCK,
                sector=stock["sector"],
                country="US",
                risk_level=RiskLevel.MEDIUM,
                cap_tier=stock["cap_tier"],
                in_universe=True,
                is_active_in_pool=False,
                direction_bias="NEUTRAL",
                long_score=0.0,
                short_score=0.0,
                fundamental_score=50.0,
                sentiment_score=0.0,
            ))
            existing[symbol] = True
            inserted += 1

    # ── TA-125 Israeli stocks ─────────────────────────────────────────────────
    tase_inserted = 0
    tase_updated = 0
    for sym, name, name_he, sector, risk_lvl, cap_tier in _TA125_STOCKS:
        all_symbols.add(sym)
        if sym in existing:
            if not existing[sym]:
                await db.execute(update(Asset).where(Asset.symbol == sym).values(in_universe=True))
                tase_updated += 1
        else:
            new_assets.append(Asset(
                symbol=sym,
                name=name,
                name_hebrew=name_he,
                exchange=Exchange.TASE,
                asset_type=AssetType.STOCK,
                sector=sector,
                country="IL",
                risk_level=risk_lvl,
                cap_tier=cap_tier,
                in_universe=True,
                is_active_in_pool=False,
                direction_bias="NEUTRAL",
                long_score=0.0,
                short_score=0.0,
                fundamental_score=50.0,
                sentiment_score=0.0,
            ))
            existing[sym] = True
            tase_inserted += 1

    if new_assets:
        db.add_all(new_assets)
        await db.flush()

    skipped = len(us_stocks) - (inserted - tase_inserted) - (updated - tase_updated)
    logger.info(
        f"[universe] complete: us_inserted={inserted - tase_inserted}, us_updated={updated - tase_updated}, "
        f"tase_inserted={tase_inserted}, tase_updated={tase_updated}, total={len(all_symbols)}"
    )
    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": max(0, skipped),
        "tase_added": tase_inserted + tase_updated,
        "total": len(all_symbols),
    }


@celery_app.task(name="load_universe", bind=True, max_retries=2)
def load_universe_task(self):
    """Weekly Celery task to refresh the stock universe from index lists."""
    import asyncio

    async def _run():
        async with AsyncSessionLocal() as db:
            async with db.begin():
                return await load_universe(db)

    try:
        result = asyncio.run(_run())
        logger.info(f"Universe loader task complete: {result}")
        return result
    except Exception as exc:
        logger.error(f"Universe loader task failed: {exc}")
        raise self.retry(exc=exc, countdown=300)
