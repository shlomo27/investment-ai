"""Filling in issuer identifiers, and finding a stock's sibling listings.

The CIK comes from the SEC's own ticker file, which is the authority: it
maps every ticker it regulates to the issuer that files for it. One request
covers the whole universe, so this is a periodic backfill rather than a
per-stock lookup.
"""
from typing import Dict, List, Optional, Sequence

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset import Asset
from app.services.share_classes.rules import Listing, choose_primary, equivalent

logger = structlog.get_logger(__name__)

#: The SEC publishes every ticker it regulates with its issuer's CIK. One
#: file, no key, no rate limit beyond politeness.
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

#: The SEC rejects requests without a contact in the User-Agent, and is
#: entitled to — it is how they reach someone whose script misbehaves.
SEC_HEADERS = {"User-Agent": "InvestmentAI research contact@investment-ai.app"}


async def fetch_ticker_ciks() -> Dict[str, str]:
    """{TICKER: CIK} for every SEC-registered ticker. Empty on failure."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=60, headers=SEC_HEADERS) as client:
            resp = await client.get(SEC_TICKERS_URL)
            resp.raise_for_status()
            raw = resp.json()
    except Exception as e:
        logger.warning("SEC ticker file unavailable", error=str(e))
        return {}

    out: Dict[str, str] = {}
    # The file is {"0": {"cik_str": 320193, "ticker": "AAPL", ...}, ...}
    for row in (raw or {}).values():
        ticker = str(row.get("ticker") or "").upper().strip()
        cik = row.get("cik_str")
        if ticker and cik is not None:
            # Zero-padded to 10 digits, the form the SEC uses everywhere else.
            out[ticker] = str(cik).zfill(10)
    return out


async def backfill_ciks(db: AsyncSession) -> dict:
    """Fill Asset.cik wherever it is missing.

    Only writes missing values. An asset whose ticker the SEC does not list
    — a foreign listing, a fund — keeps a null CIK and is simply never
    grouped, which is the safe outcome rather than a guessed one.
    """
    mapping = await fetch_ticker_ciks()
    if not mapping:
        return {"updated": 0, "reason": "sec_unavailable"}

    rows = (await db.execute(select(Asset).where(Asset.cik.is_(None)))).scalars().all()
    updated = 0
    for asset in rows:
        # SEC uses BRK-B where most providers use BRK.B; try both.
        key = asset.symbol.upper()
        cik = mapping.get(key) or mapping.get(key.replace(".", "-"))
        if cik:
            asset.cik = cik
            updated += 1
    if updated:
        await db.commit()
    logger.info("CIK backfill complete", checked=len(rows), updated=updated)
    return {"checked": len(rows), "updated": updated}


def _as_listing(asset: Asset) -> Listing:
    return Listing(
        symbol=asset.symbol,
        name=asset.name or asset.symbol,
        cik=asset.cik,
        last_price=asset.last_price,
        avg_volume=getattr(asset, "avg_volume", None),
    )


async def siblings_for(db: AsyncSession, symbol: str) -> List[dict]:
    """Other listings of the same company that are the same investment.

    Returns [] whenever anything is uncertain — no CIK, a tracking
    structure, a preferred share, a name that does not match. An empty list
    means "say nothing", which is always safe; a wrong entry would tell a
    reader that two different businesses are interchangeable.
    """
    asset = (
        await db.execute(select(Asset).where(Asset.symbol == symbol))
    ).scalar_one_or_none()
    if asset is None or not asset.cik:
        return []

    candidates = (
        await db.execute(
            select(Asset).where(Asset.cik == asset.cik, Asset.symbol != asset.symbol)
        )
    ).scalars().all()
    if not candidates:
        return []

    base = _as_listing(asset)
    matched = [c for c in candidates if equivalent(base, _as_listing(c))]
    if not matched:
        return []

    group = [base] + [_as_listing(c) for c in matched]
    primary = choose_primary(group)
    return [
        {
            "symbol": c.symbol,
            "name": c.name,
            "last_price": c.last_price,
            # Which one the system would pick for someone buying today: the
            # affordable one, then the more tradeable. Shown so the reader
            # can disagree, not so they must follow it.
            "is_primary": bool(primary and primary.symbol == c.symbol),
        }
        for c in matched
    ]


async def siblings_for_many(
    db: AsyncSession, assets: Sequence[Asset]
) -> Dict[str, List[dict]]:
    """siblings_for over a whole page of symbols, in one extra query.

    The per-symbol version costs two round-trips each. A feed of a hundred
    recommendations would await two hundred of them one after another,
    against a client timeout — the exact shape that returned an empty feed
    once before. Here the candidates for every CIK on the page are fetched
    together and the matching is done in memory, where it is pure logic.

    Symbols with no siblings are absent rather than mapped to an empty list,
    so the caller's `.get(symbol, [])` stays the single place that decides
    what "nothing to say" looks like.
    """
    ciks = {a.cik for a in assets if a.cik}
    if not ciks:
        return {}

    rows = (
        await db.execute(select(Asset).where(Asset.cik.in_(ciks)))
    ).scalars().all()
    by_cik: Dict[str, List[Asset]] = {}
    for row in rows:
        by_cik.setdefault(row.cik, []).append(row)

    out: Dict[str, List[dict]] = {}
    for asset in assets:
        if not asset.cik:
            continue
        base = _as_listing(asset)
        matched = [
            _as_listing(c)
            for c in by_cik.get(asset.cik, [])
            if c.symbol != asset.symbol and equivalent(base, _as_listing(c))
        ]
        if not matched:
            continue
        primary = choose_primary([base] + matched)
        out[asset.symbol] = [
            {
                "symbol": c.symbol,
                "name": c.name,
                "last_price": c.last_price,
                "is_primary": bool(primary and primary.symbol == c.symbol),
            }
            for c in matched
        ]
    return out


async def primary_symbol_for(db: AsyncSession, symbol: str) -> Optional[str]:
    """The listing this group should be analysed under, or None if it stands
    alone. Used to avoid analysing the same business twice."""
    sibs = await siblings_for(db, symbol)
    if not sibs:
        return None
    for s in sibs:
        if s["is_primary"]:
            return s["symbol"]
    return symbol
