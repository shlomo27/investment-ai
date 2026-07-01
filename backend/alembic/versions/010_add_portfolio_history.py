"""Add portfolio_history table for daily snapshots

Revision ID: 010
Revises: 009
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cash_balance", sa.Float(), nullable=False, server_default="0"),
        sa.Column("market_value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_pnl_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "snapshot_date", name="uq_portfolio_history_user_date"),
    )
    op.create_index("ix_portfolio_history_id", "portfolio_history", ["id"])
    op.create_index("ix_portfolio_history_user_id", "portfolio_history", ["user_id"])
    op.create_index("ix_portfolio_history_snapshot_date", "portfolio_history", ["snapshot_date"])


def downgrade() -> None:
    op.drop_table("portfolio_history")
