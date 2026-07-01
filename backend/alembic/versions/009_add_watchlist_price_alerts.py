"""Add price alert fields to watchlist

Revision ID: 009
Revises: 008
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("watchlist", sa.Column("alert_price_above", sa.Float(), nullable=True))
    op.add_column("watchlist", sa.Column("alert_price_below", sa.Float(), nullable=True))
    op.add_column("watchlist", sa.Column("alert_triggered_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("watchlist", "alert_triggered_at")
    op.drop_column("watchlist", "alert_price_below")
    op.drop_column("watchlist", "alert_price_above")
