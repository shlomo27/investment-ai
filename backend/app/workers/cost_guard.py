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


# ─── Deliberate pause ─────────────────────────────────────────────────────────
# Distinct from the outage gate below: that one is set BY a failure and cleared
# by the next success, so it cannot express "stop spending, I mean it". This is
# set by a person, survives successful analyses, and lifts only when its own
# deadline passes or someone clears it. It always carries an expiry — a kill
# switch with no deadline gets forgotten, and a system that has been silently
# dead for a fortnight is worse than one that costs money.
_PAUSE_KEY = "investment_ai:analyses_paused_until"
MAX_PAUSE_DAYS = 30


async def pause_analyses(hours: int, reason: str = "") -> dict:
    """Stop every paid analysis for `hours`. Returns the resulting state."""
    import json
    from datetime import datetime, timezone, timedelta

    hours = max(1, min(int(hours), MAX_PAUSE_DAYS * 24))
    until = datetime.now(timezone.utc) + timedelta(hours=hours)
    try:
        r = await _redis()
        await r.set(_PAUSE_KEY,
                    json.dumps({"until": until.isoformat(), "reason": reason}),
                    ex=hours * 3600)
        await r.aclose()
    except Exception as exc:
        return {"paused": False, "error": str(exc)}
    return {"paused": True, "until": until.isoformat(), "hours": hours, "reason": reason}


async def resume_analyses() -> dict:
    try:
        r = await _redis()
        await r.delete(_PAUSE_KEY)
        await r.aclose()
    except Exception as exc:
        return {"paused": False, "error": str(exc)}
    return {"paused": False}


async def get_pause_status() -> dict:
    import json

    try:
        r = await _redis()
        raw = await r.get(_PAUSE_KEY)
        ttl = await r.ttl(_PAUSE_KEY) if raw else -2
        await r.aclose()
    except Exception:
        return {"paused": False}
    if not raw:
        return {"paused": False}
    try:
        state = json.loads(raw)
    except (ValueError, TypeError):
        state = {}
    return {"paused": True, "until": state.get("until"),
            "reason": state.get("reason", ""),
            "seconds_left": max(0, ttl) if ttl and ttl > 0 else None}


async def is_analysis_paused() -> bool:
    try:
        r = await _redis()
        v = await r.get(_PAUSE_KEY)
        await r.aclose()
        return bool(v)
    except Exception:
        return False  # Redis down must not silently halt the system


async def budget_exceeded() -> bool:
    """True if analyses are paused, or a daily cap is set and today's spend
    reached it.

    The pause is folded in here rather than added as a separate check at each
    call site: every path that spends money already consults this, so one
    switch covers all of them and no future path can forget it.
    """
    if await is_analysis_paused():
        return True
    from app.core.config import settings
    cap = settings.DAILY_CLAUDE_BUDGET_USD or 0.0
    if cap <= 0:
        return False
    return (await get_today_spend()) >= cap


# ─── Decision-engine (Claude) outage gate ─────────────────────────────────────
# When the fundamental agent falls back to a 0.0 "Analysis failed" result the
# decision engine is down (out of credits / provider error). Any deep-analysis
# job that keeps running then only produces worthless 0.0 rejections. These
# helpers let every job coordinate: mark the outage once, skip while it's set,
# clear it the moment a real analysis succeeds.
_ENGINE_DOWN_KEY = "investment_ai:decision_engine_down"


async def mark_decision_engine_down(ttl: int = 1800) -> None:
    try:
        r = await _redis()
        await r.set(_ENGINE_DOWN_KEY, "1", ex=ttl)
        await r.aclose()
    except Exception:
        pass


async def is_decision_engine_down() -> bool:
    try:
        r = await _redis()
        v = await r.get(_ENGINE_DOWN_KEY)
        await r.aclose()
        return bool(v)
    except Exception:
        return False


async def clear_decision_engine_down() -> None:
    try:
        r = await _redis()
        await r.delete(_ENGINE_DOWN_KEY)
        await r.aclose()
    except Exception:
        pass


def is_engine_down_result(result: dict) -> bool:
    """True if a workflow result carries the dead-engine signature."""
    fa = (result or {}).get("fundamental_analysis") or {}
    return fa.get("confidence_score", None) == 0.0 and \
        str(fa.get("analyst_notes", "")).startswith("Analysis failed")


# ─── Market-data outage gate ──────────────────────────────────────────────────
# Refusing to analyse a stock with no verified price is correct, but on its own
# it is dangerous: if every provider is blocked, each queued symbol would abort,
# be counted as "rejected", be marked done and be dropped from the queue — the
# whole universe consumed in silence with nothing actually analysed. So a
# no-price result is treated exactly like an engine outage: requeue, don't
# charge, halt after a short streak, and shout.
_DATA_DOWN_KEY = "investment_ai:market_data_down"


async def mark_market_data_down(ttl: int = 1800) -> None:
    try:
        r = await _redis()
        await r.set(_DATA_DOWN_KEY, "1", ex=ttl)
        await r.aclose()
    except Exception:
        pass


async def is_market_data_down() -> bool:
    try:
        r = await _redis()
        v = await r.get(_DATA_DOWN_KEY)
        await r.aclose()
        return bool(v)
    except Exception:
        return False


async def clear_market_data_down() -> None:
    try:
        r = await _redis()
        await r.delete(_DATA_DOWN_KEY)
        await r.aclose()
    except Exception:
        pass


# Abort reasons that mean "we could not gather the data", never "the company
# was judged and found wanting". Both must be requeued rather than recorded.
_DATA_GAP_REASONS = {"no_price", "insufficient_fundamentals"}


def is_no_price_result(result: dict) -> bool:
    """True if the workflow aborted for want of data — no price at all, or too
    few fundamentals to judge the company on."""
    return (result or {}).get("data_fetcher_error") in _DATA_GAP_REASONS
