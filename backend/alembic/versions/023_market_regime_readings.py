"""Daily market regime readings

Revision ID: 023
Revises: 022
Create Date: 2026-11-08
"""
from alembic import op
import sqlalchemy as sa

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_regime_readings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reading", sa.String(length=12), nullable=False),
        sa.Column("committed", sa.String(length=12), nullable=False),
        sa.Column("changed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    op.create_index("ix_market_regime_readings_id", "market_regime_readings", ["id"])
    op.create_index("ix_market_regime_readings_created_at", "market_regime_readings", ["created_at"])


def downgrade() -> None:
    op.drop_table("market_regime_readings")
