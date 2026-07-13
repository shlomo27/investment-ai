"""Add personal Telegram chat id to users

Revision ID: 013
Revises: 012
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("telegram_chat_id", sa.String(32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "telegram_chat_id")
