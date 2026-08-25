"""
Provider health — which price sources are actually working right now.

Every analysis walked the full provider chain in a fixed order, starting with
Yahoo, with no memory of what happened last time. On Railway, Yahoo answers
from a blocked IP range and effectively always fails, so every single analysis
paid a Yahoo timeout before reaching a provider that works, and a slow or
rate-limited source stayed first in line no matter how many times it had just
failed. Nothing recorded any of this, which is why the recurring "no price data"
outages could only be described as "it happens sometimes".

Two things live here:

  * a record of successes and failures per provider, so the question "which
    source is failing, and how often" has an answer;
  * a circuit breaker, so a provider that has just failed repeatedly is skipped
    for a cooling period instead of being tried first every time.

The breaker never blocks everything: if every provider is open, the chain runs
in full. A stale breaker must not be the reason a price cannot be fetched.
"""
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

_PREFIX = "investment_ai:provider_health:"
# Consecutive failures before a provider is skipped. High enough that a single
# bad symbol — one that genuinely has no data anywhere — cannot trip it.
_TRIP_AFTER = 5
_COOL_OFF_SECONDS = 600
_STAT_TTL = 7 * 24 * 3600

ALL_PROVIDERS = ("yahoo", "alpaca", "fmp", "finnhub", "polygon")


async def _client():
    from app.core.config import settings
    import redis.asyncio as aioredis

    return aioredis.from_url(settings.REDIS_URL)


async def record(provider: str, ok: bool) -> None:
    """Log one outcome. Never raises — health tracking must not break a fetch."""
    try:
        client = await _client()
        try:
            pipe = client.pipeline()
            field = "ok" if ok else "fail"
            pipe.incr(f"{_PREFIX}{provider}:{field}")
            pipe.expire(f"{_PREFIX}{provider}:{field}", _STAT_TTL)
            if ok:
                pipe.delete(f"{_PREFIX}{provider}:streak")
                pipe.delete(f"{_PREFIX}{provider}:open_until")
            await pipe.execute()

            if not ok:
                streak = await client.incr(f"{_PREFIX}{provider}:streak")
                await client.expire(f"{_PREFIX}{provider}:streak", _COOL_OFF_SECONDS)
                if streak >= _TRIP_AFTER:
                    await client.set(
                        f"{_PREFIX}{provider}:open_until",
                        str(int(time.time()) + _COOL_OFF_SECONDS),
                        ex=_COOL_OFF_SECONDS,
                    )
                    logger.warning(
                        f"[provider_health] {provider} failed {streak} times in a row — "
                        f"skipping it for {_COOL_OFF_SECONDS // 60} minutes"
                    )
        finally:
            await client.aclose()
    except Exception:
        pass


async def open_circuits() -> set:
    """Providers currently being skipped. Empty set if that would be all of
    them — a chain with nothing left to try is worse than a slow one."""
    try:
        client = await _client()
        try:
            now = int(time.time())
            skipping = set()
            for name in ALL_PROVIDERS:
                raw = await client.get(f"{_PREFIX}{name}:open_until")
                if raw and int(raw) > now:
                    skipping.add(name)
        finally:
            await client.aclose()
    except Exception:
        return set()

    if len(skipping) >= len(ALL_PROVIDERS):
        logger.warning("[provider_health] every provider is tripped — ignoring the breaker")
        return set()
    return skipping


async def get_health() -> dict:
    """Per-provider counters and breaker state, for the diagnostics screen."""
    try:
        client = await _client()
        try:
            now = int(time.time())
            out = {}
            for name in ALL_PROVIDERS:
                ok = int(await client.get(f"{_PREFIX}{name}:ok") or 0)
                fail = int(await client.get(f"{_PREFIX}{name}:fail") or 0)
                streak = int(await client.get(f"{_PREFIX}{name}:streak") or 0)
                raw_open = await client.get(f"{_PREFIX}{name}:open_until")
                open_until = int(raw_open) if raw_open else 0
                total = ok + fail
                out[name] = {
                    "ok": ok,
                    "fail": fail,
                    "success_pct": round(ok / total * 100, 1) if total else None,
                    "consecutive_failures": streak,
                    "skipped_now": open_until > now,
                    "skipped_for_seconds": max(0, open_until - now),
                }
            return out
        finally:
            await client.aclose()
    except Exception as exc:
        return {"error": str(exc)}


async def reset() -> None:
    """Clear all counters and breakers (admin action)."""
    try:
        client = await _client()
        try:
            for name in ALL_PROVIDERS:
                await client.delete(
                    f"{_PREFIX}{name}:ok", f"{_PREFIX}{name}:fail",
                    f"{_PREFIX}{name}:streak", f"{_PREFIX}{name}:open_until",
                )
        finally:
            await client.aclose()
    except Exception:
        pass


def served_by(price_data: Optional[dict]) -> Optional[str]:
    """Which provider a price came from, if it was stamped."""
    if not isinstance(price_data, dict):
        return None
    return price_data.get("_price_source")
