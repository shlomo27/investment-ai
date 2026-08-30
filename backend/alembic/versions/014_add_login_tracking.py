"""Track when a user last signed in, and how many times

Needed to tell whether a prospect handed a demo account actually opened the
system. Until now the only recorded moment in an account's life was its
creation, so "we sent them credentials" and "they used it" were
indistinguishable.

Revision ID: 014
Revises: 013
Create Date: 2026-08-28
"""
from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("login_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "login_count")
    op.drop_column("users", "last_login_at")
