"""Add age_group and investment_horizon_months to users

Revision ID: 008
Revises: 007
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("age_group", sa.String(10), nullable=True))
    op.add_column("users", sa.Column("investment_horizon_months", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "investment_horizon_months")
    op.drop_column("users", "age_group")
