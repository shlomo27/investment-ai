"""Content-addressed translation cache

The app ships to the stores internationally, so analyses have to reach
readers in their own language. One analysis is produced per stock and shared
by every account, so it cannot be generated per reader — it is written in
English and translated on read.

Keying the cache on a hash of the source text rather than on a
recommendation id is what keeps the cost off the per-user path: ten thousand
readers of one analysis pay for one translation, and identical wording
appearing in two analyses is translated once.

Revision ID: 016
Revises: 015
Create Date: 2026-09-19
"""
from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("source_language", sa.String(length=10), nullable=False, server_default="en"),
        sa.Column("translated_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Uniqueness is not just tidiness: two workers translating the same
        # text concurrently is the normal case, and this makes the loser's
        # insert fail harmlessly instead of storing a duplicate.
        sa.UniqueConstraint("source_hash", "language", name="uq_translation_hash_lang"),
    )
    op.create_index("ix_translations_lookup", "translations", ["source_hash", "language"])
    op.create_index("ix_translations_id", "translations", ["id"])


def downgrade() -> None:
    op.drop_index("ix_translations_id", table_name="translations")
    op.drop_index("ix_translations_lookup", table_name="translations")
    op.drop_table("translations")
