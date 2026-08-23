"""
Master list publishing — the quarterly snapshot of the live recommendations.

The list used to be published only when an admin pressed a button, which made
it the one part of the system that drifted: the feed moved on and the
published list kept showing whatever it held when the button was last pressed,
including BUYs the committee had since walked back. An admin nudge existed to
remind whoever it was to press it again.

Publishing is now derived from the feed on a schedule, so the snapshot is a
frozen copy of a real moment rather than an artefact of when someone
remembered. The manual endpoint calls the same function.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

TOP_BUYS = 30
TOP_SELLS = 20


def current_quarter(now: datetime) -> str:
    return f"Q{(now.month - 1) // 3 + 1}-{now.year}"


async def publish_master_list(db: AsyncSession) -> Dict[str, Any]:
    """Replace the active master list with the strongest live recommendations."""
    from app.db.models.master_list import MasterListEntry
    from app.db.models.recommendation import (
        Recommendation, RecommendationStatus, RecommendationType,
    )
    from app.db.models.asset import Asset as AssetModel

    now = datetime.now(timezone.utc)
    quarter = current_quarter(now)

    approved = [
        RecommendationStatus.APPROVED,
        RecommendationStatus.PRESENTED_TO_USER,
        RecommendationStatus.ACTIONED,
    ]
    buy_types = [RecommendationType.BUY, RecommendationType.STRONG_BUY]
    sell_types = [RecommendationType.SELL, RecommendationType.STRONG_SELL]

    async def _top(types, limit):
        rows = await db.execute(
            select(Recommendation, AssetModel.name.label("asset_name"), AssetModel.sector)
            .join(AssetModel, AssetModel.id == Recommendation.asset_id)
            .where(Recommendation.recommendation_type.in_(types))
            .where(Recommendation.status.in_(approved))
            .order_by(Recommendation.confidence_score.desc())
            .limit(limit)
        )
        return rows.all()

    buy_rows = await _top(buy_types, TOP_BUYS)
    sell_rows = await _top(sell_types, TOP_SELLS)

    # Nothing live to publish — leave the previous list alone rather than
    # replacing it with an empty one. An engine outage must not blank the list.
    if not buy_rows and not sell_rows:
        logger.warning("[master_list] no live recommendations — keeping the previous list")
        return {"published": 0, "quarter": quarter, "buys": 0, "sells": 0,
                "skipped": "no live recommendations"}

    await db.execute(sa_update(MasterListEntry).values(is_active=False))

    entries = []
    seen: set = set()
    for rec, asset_name, sector in (buy_rows + sell_rows):
        # One entry per symbol — rows are confidence-sorted, so the first
        # occurrence is the best one.
        if rec.symbol in seen:
            continue
        seen.add(rec.symbol)
        entries.append(MasterListEntry(
            symbol=rec.symbol,
            asset_name=asset_name,
            recommendation_type=(rec.recommendation_type.value
                                 if hasattr(rec.recommendation_type, "value")
                                 else rec.recommendation_type),
            confidence_score=rec.confidence_score,
            target_price=rec.target_price,
            stop_loss=rec.stop_loss,
            current_price=rec.current_price_at_recommendation,
            expected_return_pct=rec.expected_return_pct,
            thesis=(rec.fundamental_analysis or {}).get("thesis"),
            sector=sector,
            quarter=quarter,
            published_at=now,
            is_active=True,
            recommendation_id=rec.id,
        ))

    db.add_all(entries)
    await db.flush()

    # Deliberately no user notification. The master list is an admin-side
    # artefact — clients see the live signals feed — so announcing it to them
    # advertised a screen they cannot open.
    logger.info(f"[master_list] published {len(entries)} entries for {quarter}")
    return {
        "published": len(entries),
        "quarter": quarter,
        "buys": len(buy_rows),
        "sells": len(sell_rows),
    }
