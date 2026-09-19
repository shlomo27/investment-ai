"""Translating analysis text, cached by content.

What this is careful about, in order of how much damage getting it wrong
would do:

  1. Numbers, tickers and method names must survive untouched. A translation
     that renders "$52.08" as "52,08 $" or turns RSI into an acronym in the
     target language has corrupted financial data, not localised it.
  2. A failure must return the ORIGINAL text, never an empty string and
     never an error. A reader seeing English on a Hebrew screen has a minor
     annoyance; a reader seeing a blank analysis has been told nothing.
  3. Cost stays off the per-user path. Everything is cached by
     hash(source text) + language, so a million readers of one analysis pay
     for one translation.
"""
import asyncio
import hashlib
from typing import Dict, List, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.languages import BY_CODE, SOURCE_LANGUAGE, is_supported
from app.db.models.translation import Translation

logger = structlog.get_logger(__name__)

#: Never send a text longer than this in one go. Analyst notes run long, and
#: a single oversized request is the one most likely to time out.
MAX_CHARS = 6000

#: Ceiling on simultaneous translation calls.
#:
#: The first reader in a new language misses the cache on every row of a
#: feed page at once. Unbounded, that is hundreds of simultaneous API calls
#: from one request — rate-limited by the provider, and slow enough to look
#: like a hang. Everyone after them is served from cache, so this only ever
#: shapes that first request.
_CONCURRENCY = asyncio.Semaphore(6)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _system_prompt(target_name: str) -> str:
    return (
        f"You translate financial analysis into {target_name}.\n\n"
        "Rules, in order of importance:\n"
        "1. NEVER alter numbers, currency amounts, percentages, dates, or "
        "ticker symbols. Reproduce them exactly as written, including the "
        "decimal separator and the currency symbol's position. $52.08 stays "
        "$52.08.\n"
        "2. Keep the English names of methods, indicators and ratios: RSI, "
        "MACD, Bollinger Bands, Wyckoff, Elliott Wave, P/E, P/B, ROE, ROA, "
        "EBITDA, FCF, DCF. These are proper names in every market. Translate "
        "the prose around them.\n"
        "3. Keep company names and ticker symbols in Latin script.\n"
        "4. Match the register: this is written for investors, so keep it "
        "precise and plain. Do not add, remove, soften or strengthen any "
        "claim — a translation that makes a recommendation sound more or "
        "less confident than the original is wrong.\n"
        "5. Return ONLY the translation. No preamble, no quotes, no notes."
    )


async def _translate_one(text: str, target: str) -> Optional[str]:
    """One call to the model. Returns None on any failure."""
    lang = BY_CODE.get(target)
    if lang is None:
        return None

    api_key = settings.OPENAI_API_KEY
    if not api_key:
        logger.warning("Translation skipped — OPENAI_API_KEY is not set")
        return None

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        async with _CONCURRENCY:
            resp = await client.chat.completions.create(
                # Translation is not a reasoning task; the cheap model is
                # the right one and keeps the per-language cost near zero.
                model=settings.OPENAI_MODEL or "gpt-4o-mini",
                messages=[
                    {"role": "system", "content": _system_prompt(lang.english_name)},
                    {"role": "user", "content": text},
                ],
                temperature=0.1,
                timeout=45,
            )
        out = (resp.choices[0].message.content or "").strip()
        return out or None
    except Exception as e:
        logger.warning("Translation call failed", target=target, error=str(e))
        return None


async def translate_texts(
    texts: Dict[str, Optional[str]],
    target: str,
    db: AsyncSession,
    source_language: str = SOURCE_LANGUAGE,
) -> Dict[str, Optional[str]]:
    """Translate a set of named fields, using and filling the cache.

    Returns a dict with the same keys. Any field that cannot be translated
    comes back with its ORIGINAL text — see the module docstring.
    """
    # Nothing to do when the reader already speaks the source language.
    if not is_supported(target) or target == source_language:
        return dict(texts)

    # Deduplicate: the same sentence in two fields is one translation.
    wanted: Dict[str, str] = {}
    for key, value in texts.items():
        if value and value.strip():
            wanted[key] = value.strip()[:MAX_CHARS]
    if not wanted:
        return dict(texts)

    unique = {_hash(v): v for v in wanted.values()}

    rows = (
        await db.execute(
            select(Translation).where(
                Translation.source_hash.in_(list(unique.keys())),
                Translation.language == target,
            )
        )
    ).scalars().all()
    cached: Dict[str, str] = {r.source_hash: r.translated_text for r in rows}

    missing = [(h, t) for h, t in unique.items() if h not in cached]
    if missing:
        results = await asyncio.gather(
            *(_translate_one(t, target) for _, t in missing),
            return_exceptions=True,
        )
        fresh: List[Translation] = []
        for (h, source_text), result in zip(missing, results):
            if isinstance(result, Exception) or not result:
                continue
            cached[h] = result
            fresh.append(
                Translation(
                    source_hash=h,
                    language=target,
                    source_language=source_language,
                    translated_text=result,
                )
            )
        if fresh:
            db.add_all(fresh)
            try:
                await db.commit()
            except Exception as e:
                # A concurrent request translating the same text first is
                # normal and harmless — the unique constraint rejects the
                # duplicate and we keep serving the text we already have.
                await db.rollback()
                logger.debug("Translation cache write skipped", error=str(e))

    out: Dict[str, Optional[str]] = {}
    for key, original in texts.items():
        source_text = wanted.get(key)
        if not source_text:
            out[key] = original
            continue
        out[key] = cached.get(_hash(source_text), original)
    return out
