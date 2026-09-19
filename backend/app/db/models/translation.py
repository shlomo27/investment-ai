"""Cached translations, addressed by content.

The cache key is a hash of the SOURCE TEXT plus the target language — not a
recommendation id. Two consequences, both deliberate:

  * Cost scales with distinct texts × languages, never with users. Ten
    thousand readers of one analysis cost exactly one translation, which is
    the same property that lets the free tier exist at all.
  * Identical wording appearing in two analyses is translated once. The
    committee reuses standard phrasings constantly, so this is not
    theoretical.

Translation of a fixed text is pure, so a cached row never needs
invalidating: if the analysis is edited its hash changes and it simply
misses.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class Translation(Base):
    __tablename__ = "translations"
    __table_args__ = (
        # The lookup is always (hash, language) — one index serves it and the
        # uniqueness that stops concurrent workers storing duplicates.
        UniqueConstraint("source_hash", "language", name="uq_translation_hash_lang"),
        Index("ix_translations_lookup", "source_hash", "language"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    #: SHA-256 of the source text. Hex, so 64 characters exactly.
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)

    #: Kept for debugging and for re-translating if a model improves. Not
    #: used as a lookup key — the hash is.
    source_language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    translated_text: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
