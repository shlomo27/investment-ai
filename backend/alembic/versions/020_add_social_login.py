"""Sign in with Apple / Google

The provider's stable user id per provider, and how the account was created
(so a passwordless account can be deleted without a password).

Revision ID: 020
Revises: 019
Create Date: 2026-10-18
"""
from alembic import op
import sqlalchemy as sa

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("apple_sub", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("google_sub", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("auth_provider", sa.String(length=16), nullable=True))
    op.create_index("ix_users_apple_sub", "users", ["apple_sub"], unique=True)
    op.create_index("ix_users_google_sub", "users", ["google_sub"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_google_sub", table_name="users")
    op.drop_index("ix_users_apple_sub", table_name="users")
    op.drop_column("users", "auth_provider")
    op.drop_column("users", "google_sub")
    op.drop_column("users", "apple_sub")
