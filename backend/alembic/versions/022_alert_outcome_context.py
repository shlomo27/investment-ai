"""Alert outcomes: S&P 500 benchmark and context

Revision ID: 022
Revises: 021
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alert_outcomes", sa.Column("spy_at_alert", sa.Float(), nullable=True))
    op.add_column("alert_outcomes", sa.Column("spy_1w", sa.Float(), nullable=True))
    op.add_column("alert_outcomes", sa.Column("spy_1m", sa.Float(), nullable=True))
    op.add_column("alert_outcomes", sa.Column("context", sa.JSON(), nullable=True))


def downgrade() -> None:
    for col in ("context", "spy_1m", "spy_1w", "spy_at_alert"):
        op.drop_column("alert_outcomes", col)
