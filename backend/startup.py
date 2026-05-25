#!/usr/bin/env python3
"""One-shot startup initialization script."""
import asyncio
import sys
import time


async def wait_for_db(max_retries: int = 30, delay: float = 2.0) -> bool:
    """Retry DB connection until available or max_retries exhausted."""
    from app.core.database import check_db_connection

    for attempt in range(1, max_retries + 1):
        ok = await check_db_connection()
        if ok:
            print(f"[startup] Database ready (attempt {attempt}/{max_retries})")
            return True
        print(f"[startup] Waiting for database... ({attempt}/{max_retries})", flush=True)
        await asyncio.sleep(delay)

    print("[startup] ERROR: Database not available after maximum retries", file=sys.stderr)
    return False


async def seed_asset_pool() -> None:
    """Seed the asset pool with a default set of tracked assets if the table is empty."""
    from sqlalchemy import select, func
    from app.core.database import AsyncSessionLocal
    from app.db.models.asset import Asset, Exchange, AssetType, RiskLevel

    DEFAULT_ASSETS = [
        # US Large-Cap Tech
        dict(symbol="AAPL",  name="Apple Inc.",          exchange=Exchange.NASDAQ, asset_type=AssetType.STOCK, risk_level=RiskLevel.MEDIUM,  sector="Technology",   country="US"),
        dict(symbol="MSFT",  name="Microsoft Corporation", exchange=Exchange.NASDAQ, asset_type=AssetType.STOCK, risk_level=RiskLevel.MEDIUM, sector="Technology",   country="US"),
        dict(symbol="GOOGL", name="Alphabet Inc.",        exchange=Exchange.NASDAQ, asset_type=AssetType.STOCK, risk_level=RiskLevel.MEDIUM,  sector="Technology",   country="US"),
        dict(symbol="AMZN",  name="Amazon.com Inc.",      exchange=Exchange.NASDAQ, asset_type=AssetType.STOCK, risk_level=RiskLevel.MEDIUM,  sector="Consumer Cyclical", country="US"),
        dict(symbol="NVDA",  name="NVIDIA Corporation",   exchange=Exchange.NASDAQ, asset_type=AssetType.STOCK, risk_level=RiskLevel.HIGH,    sector="Technology",   country="US"),
        dict(symbol="META",  name="Meta Platforms Inc.",  exchange=Exchange.NASDAQ, asset_type=AssetType.STOCK, risk_level=RiskLevel.MEDIUM,  sector="Technology",   country="US"),
        dict(symbol="TSLA",  name="Tesla Inc.",           exchange=Exchange.NASDAQ, asset_type=AssetType.STOCK, risk_level=RiskLevel.HIGH,    sector="Consumer Cyclical", country="US"),
        # Financials / Healthcare
        dict(symbol="JPM",   name="JPMorgan Chase & Co.", exchange=Exchange.NYSE,   asset_type=AssetType.STOCK, risk_level=RiskLevel.MEDIUM,  sector="Financial Services", country="US"),
        dict(symbol="JNJ",   name="Johnson & Johnson",    exchange=Exchange.NYSE,   asset_type=AssetType.STOCK, risk_level=RiskLevel.LOW,     sector="Healthcare",   country="US"),
        # ETFs
        dict(symbol="SPY",   name="SPDR S&P 500 ETF",     exchange=Exchange.NYSE,   asset_type=AssetType.ETF,   risk_level=RiskLevel.LOW,     sector="Diversified",  country="US"),
        dict(symbol="QQQ",   name="Invesco QQQ Trust",    exchange=Exchange.NASDAQ, asset_type=AssetType.ETF,   risk_level=RiskLevel.MEDIUM,  sector="Technology",   country="US"),
    ]

    async with AsyncSessionLocal() as session:
        count_result = await session.execute(select(func.count()).select_from(Asset))
        existing_count = count_result.scalar_one()

        if existing_count > 0:
            print(f"[startup] Asset pool already contains {existing_count} assets — skipping seed")
            return

        for asset_data in DEFAULT_ASSETS:
            asset = Asset(**asset_data)
            session.add(asset)

        await session.commit()
        print(f"[startup] Seeded {len(DEFAULT_ASSETS)} assets into the pool")


async def main() -> None:
    # 1. Wait for DB
    db_ready = await wait_for_db(max_retries=30, delay=2.0)
    if not db_ready:
        sys.exit(1)

    # 2. Create all tables
    try:
        # Import models so SQLAlchemy metadata is populated
        import app.db.base  # noqa: F401
        from app.core.database import create_tables
        await create_tables()
        print("[startup] Tables created/verified successfully")
    except Exception as exc:
        print(f"[startup] ERROR creating tables: {exc}", file=sys.stderr)
        sys.exit(1)

    # 3. Seed asset pool
    try:
        await seed_asset_pool()
    except Exception as exc:
        print(f"[startup] WARNING: Asset pool seeding failed: {exc}", file=sys.stderr)
        # Non-fatal: the app can still run without seeded assets

    print("[startup] Initialization complete")


if __name__ == "__main__":
    asyncio.run(main())
