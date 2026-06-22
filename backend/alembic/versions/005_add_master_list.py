"""Add master_list table

Revision ID: 005
Revises: 004
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "master_list",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("asset_name", sa.String(255), nullable=True),
        sa.Column("recommendation_type", sa.String(20), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("target_price", sa.Float(), nullable=True),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("current_price", sa.Float(), nullable=True),
        sa.Column("expected_return_pct", sa.Float(), nullable=True),
        sa.Column("thesis", sa.Text(), nullable=True),
        sa.Column("sector", sa.String(100), nullable=True),
        sa.Column("quarter", sa.String(10), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("recommendation_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_master_list_symbol", "master_list", ["symbol"])
    op.create_index("ix_master_list_quarter", "master_list", ["quarter"])
    op.create_index("ix_master_list_is_active", "master_list", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_master_list_is_active", "master_list")
    op.drop_index("ix_master_list_quarter", "master_list")
    op.drop_index("ix_master_list_symbol", "master_list")
    op.drop_table("master_list")
