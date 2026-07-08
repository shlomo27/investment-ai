"""
Cost Guard — daily Claude/AI spend tracking + hard cap.

Tracks estimated USD spent on full AI analyses per day in Redis and lets the
scan jobs stop once a configurable daily budget is hit, so a runaway loop or a
busy day can't quietly blow up the API bill. All values are ESTIMATES
(EST_COST_PER_FULL_ANALYSIS_USD per full stock analysis) — good enough for a
safety ceiling, not accounting.

Disabled by default (DAILY_CLAUDE_BUDGET_USD = 0).
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_KEY_PREFIX = "investment_ai:spend:"  # + YYYY-MM-DD
_TTL = 60 * 60 * 30  # ~30h so the daily key lives past midnight then expires


def _today_key() -> str:
    return _KEY_PREFIX + datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def _redis():
    import redis.asyncio as aioredis
    from app.core.config import settings
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def record_analysis_cost(n: int = 1) -> float:
    """Add n full-analysis units to today's spend. Returns the new day total (USD)."""
    from app.core.config import settings
    inc = settings.EST_COST_PER_FULL_ANALYSIS_USD * n
    try:
        r = await _redis()
        key = _today_key()
        new_total = await r.incrbyfloat(key, inc)
        await r.expire(key, _TTL)
        await r.aclose()
        return float(new_total)
    except Exception as exc:
        logger.debug(f"[cost_guard] record failed: {exc}")
        return 0.0


async def get_today_spend() -> float:
    try:
        r = await _redis()
        val = await r.get(_today_key())
        await r.aclose()
        return float(val or 0.0)
    except Exception:
        return 0.0


async def budget_exceeded() -> bool:
    """True if a daily cap is set (>0) and today's estimated spend reached it."""
    from app.core.config import settings
    cap = settings.DAILY_CLAUDE_BUDGET_USD or 0.0
    if cap <= 0:
        return False
    return (await get_today_spend()) >= cap
