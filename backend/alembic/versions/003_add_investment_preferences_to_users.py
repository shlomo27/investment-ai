"""Add investment preferences to users

Revision ID: 003
Revises: 002
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("investment_type", sa.String(10), nullable=False, server_default="BOTH"))
    op.add_column("users", sa.Column("allows_volatile", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("allows_leveraged", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("allows_short", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("users", "allows_short")
    op.drop_column("users", "allows_leveraged")
    op.drop_column("users", "allows_volatile")
    op.drop_column("users", "investment_type")
