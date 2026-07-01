"""
Universe Loader
Fetches S&P 500 + S&P 400 from Wikipedia and TA-125 from Wikipedia (with
hardcoded fallback) and seeds them into the assets table with
in_universe=True, is_active_in_pool=False.
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

_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
_SP400_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
_TA125_URL = "https://en.wikipedia.org/wiki/TA-125"

_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; InvestmentAI/1.0; research bot)",
}

# ─── Sector classification helpers ───────────────────────────────────────────

_TASE_SECTOR_MAP: dict[str, str] = {
    "בנקאות": "Financial", "ביטוח": "Financial", "פיננסים": "Financial",
    "נדל\"ן": "Real Estate", "בנייה": "Industrials", "תשתיות": "Industrials",
    "טכנולוגיה": "Technology", "תוכנה": "Technology", "ביטחון": "Industrials",
    "בריאות": "Healthcare", "פארמה": "Healthcare", "ביוטכנולוגיה": "Healthcare",
    "תקשורת": "Communication", "אנרגיה": "Energy", "כימיה": "Basic Materials",
    "מסחר קמעונאי": "Consumer Defensive", "מזון": "Consumer Defensive",
    "תעשייה": "Industrials", "הובלה": "Industrials",
}

def _map_tase_sector(raw: str) -> str:
    raw = raw.strip()
    for heb, eng in _TASE_SECTOR_MAP.items():
        if heb in raw:
            return eng
    return "Other"


# ─── Hardcoded TA-125 fallback (~100 major constituents) ─────────────────────
# Used when Wikipedia scrape fails or returns < 50 entries.
# Format: (yahoo_symbol, english_name, hebrew_name, sector, risk_level, cap_tier)

_TA125_FALLBACK: list[tuple] = [
    # ── Banks ─────────────────────────────────────────────────────────────────
    ("LUMI.TA",  "Bank Leumi",                "בנק לאומי",                  "Financial",          RiskLevel.LOW,    "LARGE"),
    ("POLI.TA",  "Bank Hapoalim",             "בנק הפועלים",                "Financial",          RiskLevel.LOW,    "LARGE"),
    ("DSCT.TA",  "Discount Bank",             "בנק דיסקונט",                "Financial",          RiskLevel.LOW,    "LARGE"),
    ("MIZR.TA",  "Mizrahi-Tefahot Bank",      "מזרחי טפחות",                "Financial",          RiskLevel.LOW,    "LARGE"),
    ("FTIN.TA",  "First International Bank",  "הבנק הבינלאומי הראשון",      "Financial",          RiskLevel.LOW,    "MID"),
    # ── Insurance ─────────────────────────────────────────────────────────────
    ("PHOE.TA",  "Phoenix Holdings",          "פניקס",                      "Financial",          RiskLevel.MEDIUM, "LARGE"),
    ("CLLT.TA",  "Clal Insurance",            "כלל ביטוח",                  "Financial",          RiskLevel.MEDIUM, "MID"),
    ("MGDL.TA",  "Migdal Insurance",          "מגדל",                       "Financial",          RiskLevel.MEDIUM, "MID"),
    ("MMHD.TA",  "Menorah Mivtachim",         "מנורה מבטחים",               "Financial",          RiskLevel.MEDIUM, "MID"),
    ("HREL.TA",  "Harel Insurance",           "הראל",                       "Financial",          RiskLevel.MEDIUM, "MID"),
    # ── Investment Houses / Finance ────────────────────────────────────────────
    ("IBIT.TA",  "IBI Investment House",      "IBI בית השקעות",             "Financial",          RiskLevel.MEDIUM, "MID"),
    ("FNMN.TA",  "Altshuler Shaham",          "אלטשולר שחם",                "Financial",          RiskLevel.MEDIUM, "MID"),
    # ── Technology / Software / Cyber ─────────────────────────────────────────
    ("NICE.TA",  "Nice Systems",              "נייס",                       "Technology",         RiskLevel.MEDIUM, "LARGE"),
    ("CHKP.TA",  "Check Point Software",      "צ'ק פוינט",                  "Technology",         RiskLevel.LOW,    "LARGE"),
    ("WIX.TA",   "Wix.com",                   "וויקס",                      "Technology",         RiskLevel.HIGH,   "LARGE"),
    ("NVMI.TA",  "Nova Measuring Instruments","נובה",                       "Technology",         RiskLevel.HIGH,   "MID"),
    ("TSEM.TA",  "Tower Semiconductor",       "טאואר סמיקונדקטור",          "Technology",         RiskLevel.HIGH,   "MID"),
    ("GILT.TA",  "Gilat Satellite Networks",  "גלת",                        "Technology",         RiskLevel.HIGH,   "MID"),
    ("MLAN.TA",  "Malam Team",                "מלם תים",                    "Technology",         RiskLevel.MEDIUM, "MID"),
    ("ONE.TA",   "One Software Technologies", "ון תוכנה",                   "Technology",         RiskLevel.MEDIUM, "MID"),
    ("SPNS.TA",  "Sapiens International",     "ספיינס",                     "Technology",         RiskLevel.MEDIUM, "MID"),
    ("ELRN.TA",  "Elron Electronic Ind.",     "אלרון",                      "Technology",         RiskLevel.HIGH,   "MID"),
    ("PERI.TA",  "Perion Network",            "פריון",                      "Technology",         RiskLevel.HIGH,   "MID"),
    # ── Defense / Aerospace ────────────────────────────────────────────────────
    ("ESLT.TA",  "Elbit Systems",             "אלביט מערכות",               "Industrials",        RiskLevel.MEDIUM, "LARGE"),
    ("TDRN.TA",  "Tadiran Group",             "טדיראן",                     "Industrials",        RiskLevel.MEDIUM, "MID"),
    # ── Telecom / Media ────────────────────────────────────────────────────────
    ("BEZQ.TA",  "Bezeq",                     "בזק",                        "Communication",      RiskLevel.LOW,    "LARGE"),
    ("PTNR.TA",  "Partner Communications",    "פרטנר",                      "Communication",      RiskLevel.MEDIUM, "MID"),
    ("CLBH.TA",  "Cellcom Israel",            "סלקום",                      "Communication",      RiskLevel.MEDIUM, "MID"),
    ("HOT.TA",   "HOT Telecommunications",    "הוט",                        "Communication",      RiskLevel.MEDIUM, "MID"),
    # ── Chemicals / Materials ──────────────────────────────────────────────────
    ("ICL.TA",   "ICL Group",                 "כיל",                        "Basic Materials",    RiskLevel.MEDIUM, "LARGE"),
    # ── Energy / Oil & Gas ─────────────────────────────────────────────────────
    ("DLEKG.TA", "Delek Group",               "דלק קבוצה",                  "Energy",             RiskLevel.HIGH,   "MID"),
    ("DEDR.TA",  "Delek Drilling",            "דלק קידוחים",                "Energy",             RiskLevel.HIGH,   "MID"),
    ("ENLT.TA",  "Enlight Renewable Energy",  "אנלייט",                     "Energy",             RiskLevel.MEDIUM, "MID"),
    ("NGAS.TA",  "Ratio Petroleum",           "רציו נפט",                   "Energy",             RiskLevel.HIGH,   "MID"),
    # ── Healthcare / Pharma / Biotech ──────────────────────────────────────────
    ("TEVA.TA",  "Teva Pharmaceutical",       "טבע",                        "Healthcare",         RiskLevel.MEDIUM, "LARGE"),
    ("CGEN.TA",  "Compugen",                  "קומפיוג'ן",                  "Healthcare",         RiskLevel.HIGH,   "MID"),
    ("EVGN.TA",  "Evogene",                   "אבוג'ן",                     "Healthcare",         RiskLevel.HIGH,   "MID"),
    ("DRAL.TA",  "Dr. Reddy's Israel",        "ד\"ר רדיס",                  "Healthcare",         RiskLevel.MEDIUM, "MID"),
    # ── Real Estate ────────────────────────────────────────────────────────────
    ("AZRT.TA",  "Azrieli Group",             "אזריאלי",                    "Real Estate",        RiskLevel.LOW,    "LARGE"),
    ("AMOT.TA",  "Amot Investments",          "אמות",                       "Real Estate",        RiskLevel.LOW,    "MID"),
    ("ALHE.TA",  "Alony-Hetz Properties",     "אלוני חץ",                   "Real Estate",        RiskLevel.LOW,    "MID"),
    ("GZT.TA",   "Gazit Globe",               "גזית גלוב",                  "Real Estate",        RiskLevel.MEDIUM, "LARGE"),
    ("SKBN.TA",  "Shikun & Binui",            "שיכון ובינוי",               "Industrials",        RiskLevel.MEDIUM, "MID"),
    ("ARPT.TA",  "Airport City",              "עיר הנמל",                   "Real Estate",        RiskLevel.LOW,    "MID"),
    ("BSP.TA",   "Big Shopping Centers",      "ביג",                        "Real Estate",        RiskLevel.LOW,    "MID"),
    ("BYSD.TA",  "Bayside Land",              "בייסייד",                    "Real Estate",        RiskLevel.MEDIUM, "MID"),
    ("ISRAS.TA", "Israel Canada",             "ישראל קנדה",                 "Real Estate",        RiskLevel.MEDIUM, "MID"),
    # ── Construction / Engineering ─────────────────────────────────────────────
    ("SPEN.TA",  "Shapir Engineering",        "שפיר",                       "Industrials",        RiskLevel.MEDIUM, "MID"),
    ("AFHL.TA",  "Afcon Holdings",            "אפקון",                      "Industrials",        RiskLevel.MEDIUM, "MID"),
    # ── Retail / Food / Consumer ───────────────────────────────────────────────
    ("RTLS.TA",  "Rami Levy Hashikma",        "רמי לוי",                    "Consumer Defensive", RiskLevel.MEDIUM, "MID"),
    ("SANO.TA",  "Sano Consumer Products",    "סנו",                        "Consumer Defensive", RiskLevel.LOW,    "MID"),
    ("YSCO.TA",  "Strauss Group",             "שטראוס",                     "Consumer Defensive", RiskLevel.LOW,    "MID"),
    ("OSEM.TA",  "Osem Investments",          "אסם",                        "Consumer Defensive", RiskLevel.LOW,    "MID"),
    ("MEGA.TA",  "Mega Or",                   "מגה אור",                    "Consumer Defensive", RiskLevel.MEDIUM, "MID"),
    # ── Industrial / Conglomerates ─────────────────────────────────────────────
    ("ELCO.TA",  "Elco Holdings",             "אלקו",                       "Industrials",        RiskLevel.MEDIUM, "MID"),
    ("ILCO.TA",  "Israel Corporation",        "קורפ ישראל",                 "Industrials",        RiskLevel.MEDIUM, "LARGE"),
    ("MMAN.TA",  "Maman Cargo & Terminals",   "מאמן",                       "Industrials",        RiskLevel.LOW,    "MID"),
    ("TASE.TA",  "Tel Aviv Stock Exchange",   "הבורסה לני\"ע",              "Financial",          RiskLevel.MEDIUM, "MID"),
    # ── Transport / Logistics ──────────────────────────────────────────────────
    ("ASCE.TA",  "Ashdod Port",               "נמל אשדוד",                  "Industrials",        RiskLevel.LOW,    "MID"),
    ("AMSN.TA",  "Amnon Sushi / Ameson",      "אמסון",                      "Consumer Cyclical",  RiskLevel.MEDIUM, "MID"),
    # ── Hospitality ────────────────────────────────────────────────────────────
    ("PLST.TA",  "Palastin Hotels",           "פלסטין מלונות",              "Consumer Cyclical",  RiskLevel.MEDIUM, "MID"),
    ("FATL.TA",  "Fattal Hotels",             "פתאל מלונות",                "Consumer Cyclical",  RiskLevel.MEDIUM, "MID"),
]


def _fetch_ta125_wikipedia() -> list[dict]:
    """
    Try to fetch TA-125 constituents from Wikipedia.
    Expects a table with columns containing 'symbol'/'ticker' and 'company'/'name'.
    Returns list of dicts or [] on failure.
    """
    try:
        resp = _requests.get(_TA125_URL, headers=_HTTP_HEADERS, timeout=30)
        resp.raise_for_status()
        tables = pd.read_html(resp.text)
        for df in tables:
            cols_lower = {str(c).lower(): c for c in df.columns}
            # Look for a table that has both a symbol column and a name column
            sym_col = next((cols_lower[k] for k in cols_lower if "symbol" in k or "ticker" in k or "code" in k), None)
            name_col = next((cols_lower[k] for k in cols_lower if "company" in k or "name" in k or "security" in k), None)
            if sym_col is None or name_col is None:
                continue
            sector_col = next((cols_lower[k] for k in cols_lower if "sector" in k or "industry" in k), None)
            results = []
            for _, row in df.iterrows():
                raw_sym = str(row[sym_col]).strip()
                name    = str(row[name_col]).strip()
                if not raw_sym or raw_sym == "nan" or not name or name == "nan":
                    continue
                # Normalise: TASE codes may appear without .TA suffix
                sym = raw_sym if raw_sym.endswith(".TA") else f"{raw_sym}.TA"
                sector_raw = str(row[sector_col]).strip() if sector_col else ""
                sector = _map_tase_sector(sector_raw) if sector_raw and sector_raw != "nan" else "Other"
                results.append({
                    "symbol": sym,
                    "name":   name,
                    "sector": sector,
                    "cap_tier": "MID",
                })
            if len(results) >= 50:
                logger.info(f"[universe] Fetched {len(results)} TA-125 stocks from Wikipedia")
                return results
        logger.warning("[universe] TA-125 Wikipedia table not recognised — using fallback list")
        return []
    except Exception as e:
        logger.warning(f"[universe] TA-125 Wikipedia fetch failed ({e}) — using fallback list")
        return []


def _build_ta125_list() -> list[dict]:
    """
    Returns TA-125 as a list of dicts.
    Tries Wikipedia first; falls back to the hardcoded list.
    """
    wiki = _fetch_ta125_wikipedia()
    if len(wiki) >= 50:
        return wiki

    # Build from hardcoded tuples
    return [
        {
            "symbol":    sym,
            "name":      name,
            "name_he":   name_he,
            "sector":    sector,
            "risk_level": risk_lvl,
            "cap_tier":  cap_tier,
        }
        for sym, name, name_he, sector, risk_lvl, cap_tier in _TA125_FALLBACK
    ]


# ─── US index scrapers ────────────────────────────────────────────────────────

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
            name   = str(row.get("Security", "")).strip()
            sector = str(row.get("GICS Sector", "")).strip()
            if symbol and name and symbol != "nan":
                results.append({"symbol": symbol, "name": name, "sector": sector or "Other", "cap_tier": "LARGE"})
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
            name   = str(row.get("Company", row.get("Security", row.get("Name", "")))).strip()
            sector = str(row.get("GICS Sector", row.get("Sector", ""))).strip()
            if symbol and name and symbol != "nan":
                results.append({"symbol": symbol, "name": name, "sector": sector or "Other", "cap_tier": "MID"})
        logger.info(f"Fetched {len(results)} S&P 400 constituents")
        return results
    except Exception as e:
        logger.error(f"Failed to fetch S&P 400: {e}")
        return []


def _infer_exchange(symbol: str) -> Exchange:
    nasdaq_hints = {"AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "GOOG", "AVGO", "COST"}
    return Exchange.NASDAQ if symbol in nasdaq_hints else Exchange.NYSE


# ─── Main loader ─────────────────────────────────────────────────────────────

async def load_universe(db: AsyncSession) -> dict:
    """
    Load S&P 500 + S&P 400 + TA-125 into universe.
    New symbols are inserted; existing ones get in_universe=True updated.
    Runs blocking I/O in thread pool to avoid blocking the async event loop.
    Returns {inserted, updated, skipped, tase_added, total}.
    """
    stocks_500, stocks_400, tase_stocks = await asyncio.gather(
        asyncio.to_thread(_fetch_sp500),
        asyncio.to_thread(_fetch_sp400),
        asyncio.to_thread(_build_ta125_list),
    )
    us_stocks = stocks_500 + stocks_400
    logger.info(f"[universe] S&P 500+400: {len(us_stocks)}, TA-125: {len(tase_stocks)} stocks")

    existing_result = await db.execute(select(Asset.symbol, Asset.in_universe))
    existing = {row[0]: row[1] for row in existing_result.fetchall()}

    inserted = updated = 0
    tase_inserted = tase_updated = 0
    new_assets: list[Asset] = []
    all_symbols: set[str] = set()

    # ── US stocks ─────────────────────────────────────────────────────────────
    for stock in us_stocks:
        sym = stock["symbol"]
        all_symbols.add(sym)
        if sym in existing:
            if not existing[sym]:
                await db.execute(update(Asset).where(Asset.symbol == sym).values(in_universe=True))
                updated += 1
        else:
            new_assets.append(Asset(
                symbol=sym, name=stock["name"],
                exchange=_infer_exchange(sym), asset_type=AssetType.STOCK,
                sector=stock["sector"], country="US", risk_level=RiskLevel.MEDIUM,
                cap_tier=stock["cap_tier"], in_universe=True, is_active_in_pool=False,
                direction_bias="NEUTRAL", long_score=0.0, short_score=0.0,
                fundamental_score=50.0, sentiment_score=0.0,
            ))
            existing[sym] = True
            inserted += 1

    # ── TA-125 Israeli stocks ──────────────────────────────────────────────────
    for stock in tase_stocks:
        sym = stock["symbol"]
        all_symbols.add(sym)
        if sym in existing:
            if not existing[sym]:
                await db.execute(update(Asset).where(Asset.symbol == sym).values(in_universe=True))
                tase_updated += 1
        else:
            new_assets.append(Asset(
                symbol=sym,
                name=stock["name"],
                name_hebrew=stock.get("name_he", ""),
                exchange=Exchange.TASE,
                asset_type=AssetType.STOCK,
                sector=stock.get("sector", "Other"),
                country="IL",
                risk_level=stock.get("risk_level", RiskLevel.MEDIUM),
                cap_tier=stock.get("cap_tier", "MID"),
                in_universe=True,
                is_active_in_pool=False,
                direction_bias="NEUTRAL",
                long_score=0.0, short_score=0.0,
                fundamental_score=50.0, sentiment_score=0.0,
            ))
            existing[sym] = True
            tase_inserted += 1

    if new_assets:
        db.add_all(new_assets)
        await db.flush()

    logger.info(
        f"[universe] done: us_new={inserted}, us_updated={updated}, "
        f"tase_new={tase_inserted}, tase_updated={tase_updated}, total={len(all_symbols)}"
    )
    return {
        "inserted": inserted + tase_inserted,
        "updated":  updated + tase_updated,
        "skipped":  len(us_stocks) - inserted - updated,
        "tase_added": tase_inserted + tase_updated,
        "total":    len(all_symbols),
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
