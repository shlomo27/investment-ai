"""SEC issuer identifier, for grouping share classes

Two tickers from one company must be recognised as one company, and the
name cannot do it: "Alphabet Inc." and "Alphabet Inc. Class C" are not equal
strings, while "Liberty Formula One" and "Liberty Braves" are close ones.

CIK is the SEC's identifier for the ISSUER, so it answers the question
exactly. It is necessary but not sufficient — a shared CIK also covers
tracking stocks and preferred shares, which are not the same investment at
all — so the grouping rules apply several further tests on top of it.

Nullable: the field is backfilled from SEC data, and a stock without a CIK
is simply never grouped, which is the safe answer.

Revision ID: 017
Revises: 016
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("cik", sa.String(length=12), nullable=True))
    op.create_index("ix_assets_cik", "assets", ["cik"])


def downgrade() -> None:
    op.drop_index("ix_assets_cik", table_name="assets")
    op.drop_column("assets", "cik")
