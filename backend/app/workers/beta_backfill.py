"""
Beta backfill — fills Asset.beta / Asset.risk_level for stocks that have never
had their volatility measured.

Asset.risk_level was set once, at universe load, to a literal MEDIUM for every
US stock, and Asset.beta was never written at all. The analysis pipeline now
records both, but only for a stock it re-analyses — which for a symbol outside
the pre-screener pool can be a full quarter away. Until then the card shows no
volatility band and the allows_volatile filter still has nothing real to act
on.

This job closes that gap directly: one cheap metrics call per unmeasured
symbol, Finnhub first (its free tier returns beta), FMP second.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

# Finnhub's free tier allows 60 calls/minute. One call per second leaves room
# for the schedulers that share the key.
_DELAY_SECONDS = 1.0
# Sized to cover the whole universe (S&P 500 + 400, ~900 symbols) in a single
# run. A smaller cap meant one press of the button measured less than half the
# universe and left the rest with no badge — indistinguishable, from the
# outside, from the feature not working.
_MAX_PER_RUN = 1200


def risk_level_from_beta(beta: float):
    """Single source of truth for the volatility bands — the analysis pipeline
    imports this so a backfilled stock and a freshly analysed one cannot end up
    classified by two different rules."""
    from app.db.models.asset import RiskLevel

    if beta < 0.8:
        return RiskLevel.LOW
    if beta < 1.3:
        return RiskLevel.MEDIUM
    if beta < 1.8:
        return RiskLevel.HIGH
    return RiskLevel.VERY_HIGH


async def _fetch_beta(symbol: str) -> float | None:
    """Beta from whichever provider answers. None when nobody does — a missing
    reading is left missing rather than defaulted, so it cannot be mistaken for
    a measured low value."""
    from app.services.market_data.finnhub_service import FinnhubService

    try:
        fh = FinnhubService()
        if fh.is_configured():
            metrics = await fh.get_basic_financials(symbol)
            if metrics and metrics.get("beta") is not None:
                return float(metrics["beta"])
    except Exception as exc:
        logger.debug(f"[beta_backfill] finnhub failed for {symbol}: {exc}")

    try:
        from app.services.market_data.fmp_service import FMPService

        fmp = FMPService()
        if fmp._key:
            profile = await fmp.get_stock_info(symbol)
            if profile and profile.get("beta") is not None:
                return float(profile["beta"])
    except Exception as exc:
        logger.debug(f"[beta_backfill] fmp failed for {symbol}: {exc}")

    return None


async def job_backfill_beta(limit: int = _MAX_PER_RUN) -> dict:
    """Measure volatility for universe stocks that have never been measured."""
    from app.core.database import AsyncSessionLocal
    from app.db.models.asset import Asset
    from app.db.models.recommendation import Recommendation, RecommendationStatus
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(Asset.symbol)
            .where(Asset.in_universe == True, Asset.beta.is_(None))
            .order_by(Asset.symbol)
            .limit(limit)
        )
        symbols = [r[0] for r in rows.all()]

        # Stocks the user is actually looking at go first. Measuring the
        # universe in plain alphabetical order meant a run that stopped early
        # left every symbol late in the alphabet without a badge — a card for
        # VRTX stayed blank while GOOGL had one, which reads as a broken
        # feature rather than as an unfinished pass.
        on_screen = {r[0] for r in (await db.execute(
            select(Recommendation.symbol).where(
                Recommendation.status.in_([
                    RecommendationStatus.APPROVED,
                    RecommendationStatus.PRESENTED_TO_USER,
                    RecommendationStatus.ACTIONED,
                ])
            ).distinct()
        )).all()}

    symbols.sort(key=lambda s: (s not in on_screen, s))

    if not symbols:
        return {"updated": 0, "attempted": 0, "reason": "every universe stock already has a beta"}

    updated = 0
    missing = 0
    for symbol in symbols:
        beta = await _fetch_beta(symbol)
        if beta is None or not (0 < beta < 10):
            missing += 1
        else:
            async with AsyncSessionLocal() as db:
                asset = (await db.execute(
                    select(Asset).where(Asset.symbol == symbol)
                )).scalar_one_or_none()
                if asset is not None:
                    asset.beta = beta
                    asset.risk_level = risk_level_from_beta(beta)
                    await db.commit()
                    updated += 1
        await asyncio.sleep(_DELAY_SECONDS)

    logger.info(f"[beta_backfill] measured {updated}/{len(symbols)} symbols "
                f"({missing} had no beta from any provider)")
    return {"updated": updated, "attempted": len(symbols), "no_data": missing}
