"""Add outcome tracking fields to recommendations

Revision ID: 007
Revises: 006
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recommendations", sa.Column("outcome_price", sa.Float(), nullable=True))
    op.add_column("recommendations", sa.Column("outcome_return_pct", sa.Float(), nullable=True))
    op.add_column("recommendations", sa.Column("outcome_vs_market_pct", sa.Float(), nullable=True))
    op.add_column("recommendations", sa.Column("outcome_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("recommendations", sa.Column("outcome_tracked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("recommendations", sa.Column("outcome_result", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("recommendations", "outcome_result")
    op.drop_column("recommendations", "outcome_tracked_at")
    op.drop_column("recommendations", "outcome_date")
    op.drop_column("recommendations", "outcome_vs_market_pct")
    op.drop_column("recommendations", "outcome_return_pct")
    op.drop_column("recommendations", "outcome_price")
