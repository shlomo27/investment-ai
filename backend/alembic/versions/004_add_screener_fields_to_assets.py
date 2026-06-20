"""Add screener fields to assets

Revision ID: 004
Revises: 003
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("cap_tier", sa.String(10), nullable=False, server_default="LARGE"))
    op.add_column("assets", sa.Column("in_universe", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("assets", sa.Column("direction_bias", sa.String(10), nullable=False, server_default="NEUTRAL"))
    op.add_column("assets", sa.Column("long_score", sa.Float(), nullable=False, server_default="0.0"))
    op.add_column("assets", sa.Column("short_score", sa.Float(), nullable=False, server_default="0.0"))
    op.add_column("assets", sa.Column("screener_activated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_assets_in_universe", "assets", ["in_universe"])


def downgrade() -> None:
    op.drop_index("ix_assets_in_universe", "assets")
    op.drop_column("assets", "screener_activated_at")
    op.drop_column("assets", "short_score")
    op.drop_column("assets", "long_score")
    op.drop_column("assets", "direction_bias")
    op.drop_column("assets", "in_universe")
    op.drop_column("assets", "cap_tier")
