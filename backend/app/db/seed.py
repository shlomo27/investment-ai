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
    ("AAPL",  "Apple Inc.",              Exchange.NASDAQ, "Technology",        "US", RiskLevel.MEDIUM),
    ("MSFT",  "Microsoft Corp.",         Exchange.NASDAQ, "Technology",        "US", RiskLevel.LOW),
    ("GOOGL", "Alphabet Inc.",           Exchange.NASDAQ, "Technology",        "US", RiskLevel.MEDIUM),
    ("AMZN",  "Amazon.com Inc.",         Exchange.NASDAQ, "Consumer Cyclical", "US", RiskLevel.MEDIUM),
    ("NVDA",  "NVIDIA Corp.",            Exchange.NASDAQ, "Technology",        "US", RiskLevel.HIGH),
    ("META",  "Meta Platforms",          Exchange.NASDAQ, "Technology",        "US", RiskLevel.MEDIUM),
    ("TSLA",  "Tesla Inc.",              Exchange.NASDAQ, "Consumer Cyclical", "US", RiskLevel.HIGH),
    ("JPM",   "JPMorgan Chase",          Exchange.NYSE,   "Financial",         "US", RiskLevel.LOW),
    ("JNJ",   "Johnson & Johnson",       Exchange.NYSE,   "Healthcare",        "US", RiskLevel.LOW),
    ("V",     "Visa Inc.",               Exchange.NYSE,   "Financial",         "US", RiskLevel.LOW),
    ("ADBE",  "Adobe Inc.",              Exchange.NASDAQ, "Technology",        "US", RiskLevel.MEDIUM),
    ("CRM",   "Salesforce Inc.",         Exchange.NYSE,   "Technology",        "US", RiskLevel.MEDIUM),
    ("NFLX",  "Netflix Inc.",            Exchange.NASDAQ, "Communication",     "US", RiskLevel.HIGH),
    ("AMD",   "Advanced Micro Devices",  Exchange.NASDAQ, "Technology",        "US", RiskLevel.HIGH),
    ("INTC",  "Intel Corp.",             Exchange.NASDAQ, "Technology",        "US", RiskLevel.MEDIUM),
]

_TASE_STOCKS = [
    # symbol, name, name_hebrew, sector
    ("1082373", "Bank Leumi",   "בנק לאומי",                    "Financial"),
    ("1084763", "Bank Hapoalim","בנק הפועלים",                  "Financial"),
    ("1081316", "Teva Pharma",  "טבע תעשיות פרמצבטיות",         "Healthcare"),
    ("5122120", "Nice Systems", "נייס סיסטמס",                  "Technology"),
    ("1100858", "Check Point",  "צ'ק פוינט",                    "Technology"),
]


async def seed_asset_pool(db: AsyncSession) -> dict:
    """Seed initial assets. Returns {inserted: N, skipped: N}"""

    # Fetch all existing symbols in one query
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

    # TASE stocks
    for symbol, name, name_hebrew, sector in _TASE_STOCKS:
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
            risk_level=RiskLevel.MEDIUM,
            is_active_in_pool=True,
            fundamental_score=50.0,
            sentiment_score=0.0,
        ))
        inserted += 1

    if new_assets:
        db.add_all(new_assets)
        await db.flush()

    return {"inserted": inserted, "skipped": skipped}
