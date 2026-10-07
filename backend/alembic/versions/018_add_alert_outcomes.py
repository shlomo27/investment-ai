"""Alert outcomes, to measure whether alerts are right

Each alert records the price it went out at; a daily job fills in the price
about a week and a month later, so the hit rate of each kind of alert can be
shown instead of argued from one stock.

Revision ID: 018
Revises: 017
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("signal", sa.String(length=20), nullable=False),
        sa.Column("price_at_alert", sa.Float(), nullable=False),
        sa.Column("recommendation_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("price_1w", sa.Float(), nullable=True),
        sa.Column("price_1m", sa.Float(), nullable=True),
    )
    op.create_index("ix_alert_outcomes_id", "alert_outcomes", ["id"])
    op.create_index("ix_alert_outcomes_symbol", "alert_outcomes", ["symbol"])
    op.create_index("ix_alert_outcomes_kind", "alert_outcomes", ["kind"])
    op.create_index("ix_alert_outcomes_created_at", "alert_outcomes", ["created_at"])


def downgrade() -> None:
    op.drop_table("alert_outcomes")
