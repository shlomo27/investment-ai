"""Opt-out for market-regime alerts

Revision ID: 021
Revises: 020
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("notify_market_regime", sa.Boolean(),
                                     nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("users", "notify_market_regime")
