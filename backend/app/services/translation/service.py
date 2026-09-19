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


#: Scripts that identify a language on sight. Latin is deliberately absent:
#: English, German, Spanish, French, Italian and Portuguese all share it, so
#: script tells us nothing about which of them a text is in.
_SCRIPTS = {
    "he": (0x0590, 0x05FF),
    "ar": (0x0600, 0x06FF),
    "ja": (0x3040, 0x30FF),   # kana; kanji alone is ambiguous with Chinese
    "ko": (0xAC00, 0xD7AF),   # hangul syllables
}


def detect_source_language(text: str) -> Optional[str]:
    """Which language a text is already in, when the script makes it obvious.

    This exists because the stored analyses are not all English. The agents
    wrote Hebrew until the international launch, so the database holds a mix:
    older rows in Hebrew, newer ones in English. Assuming English for all of
    them would mean a Hebrew reader paying to "translate" Hebrew into Hebrew,
    and — worse — an English reader being handed Hebrew untouched, because
    target == assumed source looks like a no-op.

    Returns None for anything in Latin script, where the script cannot
    distinguish English from German. That is the safe answer: unknown means
    "translate it", and translating text that is already in the target
    language is wasteful but harmless, while skipping text that is not is
    a reader who cannot read their own screen.
    """
    if not text:
        return None
    sample = text[:400]
    letters = [c for c in sample if c.isalpha()]
    if not letters:
        return None
    for code, (lo, hi) in _SCRIPTS.items():
        hits = sum(1 for c in letters if lo <= ord(c) <= hi)
        # A third is enough: analyses mix in Latin tickers and numbers, so a
        # Hebrew paragraph is never purely Hebrew characters.
        if hits / len(letters) > 0.33:
            return code
    return None


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _system_prompt(target_name: str, company: Optional[str] = None) -> str:
    """Instructions for one translation.

    `company` matters more than it looks. The older analyses are Hebrew, and
    the agent transliterated company names into Hebrew script — "Fiserv"
    became "פיזרב". Translating that to French, the model has no way to know
    it is a real company and renders it phonetically: "Pizerb". The name on
    a financial screen is then simply wrong. Naming the company explicitly
    lets it be restored rather than re-spelled.
    """
    named = (
        f"\n\nTHE COMPANY: this text is about {company}. Wherever the company "
        f"is referred to — including transliterated into another script — "
        f"write exactly \"{company}\". Never spell it phonetically."
        if company
        else ""
    )
    return (
        f"You translate financial analysis into {target_name}.{named}\n\n"
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


async def _translate_one(
    text: str, target: str, company: Optional[str] = None
) -> Optional[str]:
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
                    {"role": "system", "content": _system_prompt(lang.english_name, company)},
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
    company: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """Translate a set of named fields, using and filling the cache.

    Returns a dict with the same keys. Any field that cannot be translated
    comes back with its ORIGINAL text — see the module docstring.
    """
    # An unsupported target has nothing to translate into. The reader's
    # language matching the nominal source is NOT a reason to skip: the
    # stored text may be in neither, which is exactly the case for every
    # analysis written before the international launch.
    if not is_supported(target):
        return dict(texts)

    # Deduplicate: the same sentence in two fields is one translation.
    #
    # A text already written in the target language is skipped outright. The
    # stored analyses are a mix of Hebrew (written before the international
    # launch) and English, so this is checked per text rather than assumed
    # once for the whole table.
    wanted: Dict[str, str] = {}
    for key, value in texts.items():
        if not value or not value.strip():
            continue
        body = value.strip()[:MAX_CHARS]
        detected = detect_source_language(body)
        if detected == target:
            continue
        # Latin script with English as the target: assume it is already
        # English. Detection cannot tell English from German, but the source
        # language IS English, so a Latin-script analysis being anything else
        # is not a case that exists. Without this every English reader pays
        # to translate English into English.
        if detected is None and target == source_language:
            continue
        wanted[key] = body
    if not wanted:
        return dict(texts)

    # The company name is part of the key: a translation produced without it
    # spells the name phonetically, and caching that under the same key as a
    # correct one would serve the wrong name forever.
    salt = f"|{company}" if company else ""
    unique = {_hash(v + salt): v for v in wanted.values()}

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
            *(_translate_one(t, target, company) for _, t in missing),
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
        out[key] = cached.get(_hash(source_text + salt), original)
    return out
