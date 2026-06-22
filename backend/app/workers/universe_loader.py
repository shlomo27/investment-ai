"""
Universe Loader
Fetches S&P 500 + S&P 400 constituent lists from Wikipedia and seeds them
into the assets table with in_universe=True, is_active_in_pool=False.
Run as a Celery task (weekly) or call load_universe() directly.
"""
import asyncio
import logging
from datetime import datetime, timezone
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
    Load S&P 500 + S&P 400 into universe.
    New symbols are inserted; existing symbols get in_universe=True updated.
    Runs Wikipedia fetches in thread pool to avoid blocking the async event loop.
    Returns {inserted, updated, skipped}.
    """
    # Run blocking HTTP+pandas calls in thread pool so the event loop stays free
    stocks_500, stocks_400 = await asyncio.gather(
        asyncio.to_thread(_fetch_sp500),
        asyncio.to_thread(_fetch_sp400),
    )
    stocks = stocks_500 + stocks_400

    if not stocks:
        return {"inserted": 0, "updated": 0, "skipped": 0, "error": "Failed to fetch index data from Wikipedia"}

    # Load all existing symbols
    existing_result = await db.execute(select(Asset.symbol, Asset.in_universe))
    existing = {row[0]: row[1] for row in existing_result.fetchall()}

    inserted = 0
    updated = 0
    new_assets = []
    sp_symbols: set[str] = set()

    for stock in stocks:
        symbol = stock["symbol"]
        sp_symbols.add(symbol)

        if symbol in existing:
            if not existing[symbol]:
                # Exists but wasn't marked in_universe — fix it
                await db.execute(
                    update(Asset)
                    .where(Asset.symbol == symbol)
                    .values(in_universe=True)
                )
                updated += 1
            else:
                pass  # already correct
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

    if new_assets:
        db.add_all(new_assets)
        await db.flush()

    skipped = len(stocks) - inserted - updated
    logger.info(f"Universe load complete: inserted={inserted}, updated={updated}, skipped={skipped}, total_sp={len(sp_symbols)}")
    return {"inserted": inserted, "updated": updated, "skipped": skipped, "total": len(sp_symbols)}


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
