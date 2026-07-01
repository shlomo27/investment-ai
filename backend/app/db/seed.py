"""
Asset pool seeder.
Run via the /market/pool/seed endpoint or directly from a management script.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset import Asset, Exchange, AssetType, RiskLevel

# ---------------------------------------------------------------------------
# Curated stock list
# ---------------------------------------------------------------------------

_US_STOCKS = [
    # symbol, name, exchange, sector, country, risk_level

    # ── US Mega Cap Tech ──────────────────────────────────────────────────
    ("AAPL",  "Apple Inc.",                Exchange.NASDAQ, "Technology",          "US", RiskLevel.MEDIUM),
    ("MSFT",  "Microsoft Corp.",           Exchange.NASDAQ, "Technology",          "US", RiskLevel.LOW),
    ("GOOGL", "Alphabet Inc.",             Exchange.NASDAQ, "Technology",          "US", RiskLevel.MEDIUM),
    ("AMZN",  "Amazon.com Inc.",           Exchange.NASDAQ, "Consumer Cyclical",   "US", RiskLevel.MEDIUM),
    ("NVDA",  "NVIDIA Corp.",              Exchange.NASDAQ, "Technology",          "US", RiskLevel.HIGH),
    ("META",  "Meta Platforms",            Exchange.NASDAQ, "Technology",          "US", RiskLevel.MEDIUM),
    ("TSLA",  "Tesla Inc.",                Exchange.NASDAQ, "Consumer Cyclical",   "US", RiskLevel.HIGH),
    ("ADBE",  "Adobe Inc.",                Exchange.NASDAQ, "Technology",          "US", RiskLevel.MEDIUM),
    ("CRM",   "Salesforce Inc.",           Exchange.NYSE,   "Technology",          "US", RiskLevel.MEDIUM),
    ("NFLX",  "Netflix Inc.",              Exchange.NASDAQ, "Communication",       "US", RiskLevel.HIGH),
    ("AMD",   "Advanced Micro Devices",    Exchange.NASDAQ, "Technology",          "US", RiskLevel.HIGH),
    ("INTC",  "Intel Corp.",               Exchange.NASDAQ, "Technology",          "US", RiskLevel.MEDIUM),
    ("AVGO",  "Broadcom Inc.",             Exchange.NASDAQ, "Technology",          "US", RiskLevel.MEDIUM),
    ("ORCL",  "Oracle Corp.",              Exchange.NYSE,   "Technology",          "US", RiskLevel.MEDIUM),
    ("QCOM",  "Qualcomm Inc.",             Exchange.NASDAQ, "Technology",          "US", RiskLevel.MEDIUM),

    # ── US Financials ─────────────────────────────────────────────────────
    ("JPM",   "JPMorgan Chase",            Exchange.NYSE,   "Financial",           "US", RiskLevel.LOW),
    ("V",     "Visa Inc.",                 Exchange.NYSE,   "Financial",           "US", RiskLevel.LOW),
    ("MA",    "Mastercard Inc.",           Exchange.NYSE,   "Financial",           "US", RiskLevel.LOW),
    ("BAC",   "Bank of America",           Exchange.NYSE,   "Financial",           "US", RiskLevel.MEDIUM),
    ("GS",    "Goldman Sachs",             Exchange.NYSE,   "Financial",           "US", RiskLevel.MEDIUM),
    ("BRK-B", "Berkshire Hathaway B",      Exchange.NYSE,   "Financial",           "US", RiskLevel.LOW),

    # ── US Healthcare ─────────────────────────────────────────────────────
    ("JNJ",   "Johnson & Johnson",         Exchange.NYSE,   "Healthcare",          "US", RiskLevel.LOW),
    ("LLY",   "Eli Lilly",                 Exchange.NYSE,   "Healthcare",          "US", RiskLevel.MEDIUM),
    ("UNH",   "UnitedHealth Group",        Exchange.NYSE,   "Healthcare",          "US", RiskLevel.LOW),
    ("PFE",   "Pfizer Inc.",               Exchange.NYSE,   "Healthcare",          "US", RiskLevel.MEDIUM),
    ("ABBV",  "AbbVie Inc.",               Exchange.NYSE,   "Healthcare",          "US", RiskLevel.MEDIUM),
    ("MRNA",  "Moderna Inc.",              Exchange.NASDAQ, "Healthcare",          "US", RiskLevel.HIGH),

    # ── US Energy ─────────────────────────────────────────────────────────
    ("XOM",   "Exxon Mobil",               Exchange.NYSE,   "Energy",              "US", RiskLevel.MEDIUM),
    ("CVX",   "Chevron Corp.",             Exchange.NYSE,   "Energy",              "US", RiskLevel.MEDIUM),

    # ── US Consumer ───────────────────────────────────────────────────────
    ("COST",  "Costco Wholesale",          Exchange.NASDAQ, "Consumer Defensive",  "US", RiskLevel.LOW),
    ("WMT",   "Walmart Inc.",              Exchange.NYSE,   "Consumer Defensive",  "US", RiskLevel.LOW),
    ("MCD",   "McDonald's Corp.",          Exchange.NYSE,   "Consumer Defensive",  "US", RiskLevel.LOW),
    ("DIS",   "Walt Disney Co.",           Exchange.NYSE,   "Communication",       "US", RiskLevel.MEDIUM),
    ("SPOT",  "Spotify Technology",        Exchange.NYSE,   "Communication",       "US", RiskLevel.HIGH),

    # ── US Industrial / Other ─────────────────────────────────────────────
    ("CAT",   "Caterpillar Inc.",          Exchange.NYSE,   "Industrials",         "US", RiskLevel.MEDIUM),
    ("BA",    "Boeing Co.",                Exchange.NYSE,   "Industrials",         "US", RiskLevel.HIGH),
    ("UBER",  "Uber Technologies",         Exchange.NYSE,   "Technology",          "US", RiskLevel.HIGH),
    ("SHOP",  "Shopify Inc.",              Exchange.NYSE,   "Technology",          "CA", RiskLevel.HIGH),
]

# International companies — traded on US exchanges as ADR or direct listing
# These trade in USD and yfinance provides full data
_INTERNATIONAL_US_LISTED = [
    # symbol, name, exchange, sector, country, risk_level

    # ── Europe (ADR / direct US listing) ─────────────────────────────────
    ("ASML",  "ASML Holding",              Exchange.NASDAQ, "Technology",          "NL", RiskLevel.MEDIUM),
    ("NVO",   "Novo Nordisk",              Exchange.NYSE,   "Healthcare",          "DK", RiskLevel.MEDIUM),
    ("SAP",   "SAP SE",                    Exchange.NYSE,   "Technology",          "DE", RiskLevel.LOW),
    ("SHEL",  "Shell PLC",                 Exchange.NYSE,   "Energy",              "GB", RiskLevel.MEDIUM),
    ("AZN",   "AstraZeneca PLC",           Exchange.NASDAQ, "Healthcare",          "GB", RiskLevel.MEDIUM),
    ("UL",    "Unilever PLC",              Exchange.NYSE,   "Consumer Defensive",  "GB", RiskLevel.LOW),
    ("LVMUY", "LVMH Moët Hennessy",        Exchange.OTHER,  "Consumer Cyclical",   "FR", RiskLevel.MEDIUM),
    ("SIEGY", "Siemens AG",                Exchange.OTHER,  "Industrials",         "DE", RiskLevel.LOW),

    # ── Asia / Global (ADR / direct US listing) ───────────────────────────
    ("TSM",   "Taiwan Semiconductor",      Exchange.NYSE,   "Technology",          "TW", RiskLevel.MEDIUM),
    ("BABA",  "Alibaba Group",             Exchange.NYSE,   "Consumer Cyclical",   "CN", RiskLevel.HIGH),
    ("SE",    "Sea Limited",               Exchange.NYSE,   "Technology",          "SG", RiskLevel.HIGH),
    ("MELI",  "MercadoLibre Inc.",         Exchange.NASDAQ, "Consumer Cyclical",   "AR", RiskLevel.HIGH),
    ("TM",    "Toyota Motor Corp.",        Exchange.NYSE,   "Consumer Cyclical",   "JP", RiskLevel.LOW),
    ("SONY",  "Sony Group Corp.",          Exchange.NYSE,   "Consumer Cyclical",   "JP", RiskLevel.MEDIUM),
    ("INFY",  "Infosys Ltd.",              Exchange.NYSE,   "Technology",          "IN", RiskLevel.MEDIUM),
]

# Major ETFs — broad market exposure
_ETFS = [
    # symbol, name, exchange, sector, country, risk_level
    ("SPY",  "SPDR S&P 500 ETF",          Exchange.NYSE,   "ETF",                 "US", RiskLevel.LOW),
    ("QQQ",  "Invesco QQQ Trust",         Exchange.NASDAQ, "ETF",                 "US", RiskLevel.MEDIUM),
    ("VTI",  "Vanguard Total Market ETF", Exchange.NYSE,   "ETF",                 "US", RiskLevel.LOW),
    ("GLD",  "SPDR Gold Shares",          Exchange.NYSE,   "ETF",                 "US", RiskLevel.MEDIUM),
    ("EEM",  "iShares MSCI Emerging ETF", Exchange.NYSE,   "ETF",                 "US", RiskLevel.HIGH),
    ("EFA",  "iShares MSCI EAFE ETF",     Exchange.NYSE,   "ETF",                 "US", RiskLevel.MEDIUM),
]

_TASE_STOCKS = [
    # symbol (.TA format for yfinance), name, name_hebrew, sector, risk_level
    # ── Banks ──────────────────────────────────────────────────────────────
    ("LUMI.TA",  "Bank Leumi",                "בנק לאומי",             "Financial",          RiskLevel.LOW),
    ("POLI.TA",  "Bank Hapoalim",             "בנק הפועלים",           "Financial",          RiskLevel.LOW),
    ("DSCT.TA",  "Discount Bank",             "בנק דיסקונט",           "Financial",          RiskLevel.LOW),
    ("MIZR.TA",  "Mizrahi-Tefahot Bank",      "מזרחי טפחות",           "Financial",          RiskLevel.LOW),
    ("FTIN.TA",  "First International Bank",  "הבנק הבינלאומי",        "Financial",          RiskLevel.LOW),
    # ── Insurance ──────────────────────────────────────────────────────────
    ("PHOE.TA",  "Phoenix Holdings",          "פניקס",                 "Financial",          RiskLevel.MEDIUM),
    ("CLLT.TA",  "Clal Insurance",            "כלל ביטוח",             "Financial",          RiskLevel.MEDIUM),
    ("MGDL.TA",  "Migdal Insurance",          "מגדל",                  "Financial",          RiskLevel.MEDIUM),
    ("MMHD.TA",  "Menorah Mivtachim",         "מנורה מבטחים",          "Financial",          RiskLevel.MEDIUM),
    # ── Technology / Cyber / Defense ───────────────────────────────────────
    ("NICE.TA",  "Nice Systems",              "נייס",                  "Technology",         RiskLevel.MEDIUM),
    ("CHKP.TA",  "Check Point Software",      "צ'ק פוינט",             "Technology",         RiskLevel.LOW),
    ("WIX.TA",   "Wix.com",                   "וויקס",                 "Technology",         RiskLevel.HIGH),
    ("ESLT.TA",  "Elbit Systems",             "אלביט מערכות",          "Industrials",        RiskLevel.MEDIUM),
    ("TSEM.TA",  "Tower Semiconductor",       "טאואר סמיקונדקטור",     "Technology",         RiskLevel.HIGH),
    # ── Telecom ────────────────────────────────────────────────────────────
    ("BEZQ.TA",  "Bezeq",                     "בזק",                   "Communication",      RiskLevel.LOW),
    ("PTNR.TA",  "Partner Communications",    "פרטנר",                 "Communication",      RiskLevel.MEDIUM),
    ("CLBH.TA",  "Cellcom Israel",            "סלקום",                 "Communication",      RiskLevel.MEDIUM),
    # ── Chemicals / Materials ──────────────────────────────────────────────
    ("ICL.TA",   "ICL Group",                 "כיל",                   "Basic Materials",    RiskLevel.MEDIUM),
    # ── Energy ─────────────────────────────────────────────────────────────
    ("DLEKG.TA", "Delek Group",               "דלק קבוצה",             "Energy",             RiskLevel.HIGH),
    ("ENLT.TA",  "Enlight Renewable Energy",  "אנלייט",                "Energy",             RiskLevel.MEDIUM),
    # ── Healthcare / Pharma ────────────────────────────────────────────────
    ("TEVA.TA",  "Teva Pharmaceutical",       "טבע",                   "Healthcare",         RiskLevel.MEDIUM),
    # ── Real Estate ────────────────────────────────────────────────────────
    ("AZRT.TA",  "Azrieli Group",             "אזריאלי",               "Real Estate",        RiskLevel.LOW),
    ("AMOT.TA",  "Amot Investments",          "אמות",                  "Real Estate",        RiskLevel.LOW),
    ("SPEN.TA",  "Shapir Engineering",        "שפיר",                  "Industrials",        RiskLevel.MEDIUM),
    ("ALHE.TA",  "Alony-Hetz Properties",     "אלוני חץ",              "Real Estate",        RiskLevel.LOW),
    # ── Retail / Consumer ──────────────────────────────────────────────────
    ("RTLS.TA",  "Rami Levy Hashikma",        "רמי לוי",               "Consumer Defensive", RiskLevel.MEDIUM),
    ("SANO.TA",  "Sano Consumer Products",    "סנו",                   "Consumer Defensive", RiskLevel.LOW),
    # ── Industrial / Conglomerates ─────────────────────────────────────────
    ("ELCO.TA",  "Elco Holdings",             "אלקו",                  "Industrials",        RiskLevel.MEDIUM),
    ("ILCO.TA",  "Israel Corporation",        "קורפ ישראל",            "Industrials",        RiskLevel.MEDIUM),
]


async def seed_asset_pool(db: AsyncSession) -> dict:
    """Seed initial assets. Returns {inserted: N, skipped: N}"""

    existing_result = await db.execute(select(Asset.symbol))
    existing_symbols = {row[0] for row in existing_result.fetchall()}

    inserted = 0
    skipped = 0
    new_assets = []

    # US stocks
    for symbol, name, exchange, sector, country, risk_level in _US_STOCKS:
        if symbol in existing_symbols:
            skipped += 1
            continue
        new_assets.append(Asset(
            symbol=symbol,
            name=name,
            exchange=exchange,
            asset_type=AssetType.STOCK,
            sector=sector,
            country=country,
            risk_level=risk_level,
            is_active_in_pool=True,
            fundamental_score=50.0,
            sentiment_score=0.0,
        ))
        inserted += 1

    # International stocks (US-listed ADRs)
    for symbol, name, exchange, sector, country, risk_level in _INTERNATIONAL_US_LISTED:
        if symbol in existing_symbols:
            skipped += 1
            continue
        new_assets.append(Asset(
            symbol=symbol,
            name=name,
            exchange=exchange,
            asset_type=AssetType.STOCK,
            sector=sector,
            country=country,
            risk_level=risk_level,
            is_active_in_pool=True,
            fundamental_score=50.0,
            sentiment_score=0.0,
        ))
        inserted += 1

    # ETFs
    for symbol, name, exchange, sector, country, risk_level in _ETFS:
        if symbol in existing_symbols:
            skipped += 1
            continue
        new_assets.append(Asset(
            symbol=symbol,
            name=name,
            exchange=exchange,
            asset_type=AssetType.ETF,
            sector=sector,
            country=country,
            risk_level=risk_level,
            is_active_in_pool=True,
            fundamental_score=50.0,
            sentiment_score=0.0,
        ))
        inserted += 1

    # TASE stocks
    for symbol, name, name_hebrew, sector, risk_level in _TASE_STOCKS:
        if symbol in existing_symbols:
            skipped += 1
            continue
        new_assets.append(Asset(
            symbol=symbol,
            name=name,
            name_hebrew=name_hebrew,
            exchange=Exchange.TASE,
            asset_type=AssetType.STOCK,
            sector=sector,
            country="IL",
            risk_level=risk_level,
            in_universe=True,
            is_active_in_pool=True,
            fundamental_score=50.0,
            sentiment_score=0.0,
        ))
        inserted += 1

    if new_assets:
        db.add_all(new_assets)
        await db.flush()

    return {"inserted": inserted, "skipped": skipped}
