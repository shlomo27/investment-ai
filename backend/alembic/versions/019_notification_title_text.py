"""Notification title as TEXT

The title carries the whole alert — it is what Telegram sends and what the
inbox shows — and String(255) was too short for it. A 359-character alert
failed the insert on Postgres, send_notification caught the error and
rolled back, and the alert reached neither the inbox nor Telegram.

VARCHAR -> TEXT on Postgres changes only the type's length check; no table
rewrite, safe on a live table.

Revision ID: 019
Revises: 018
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("notifications", "title",
                    type_=sa.Text(), existing_type=sa.String(length=255),
                    existing_nullable=True)


def downgrade() -> None:
    op.alter_column("notifications", "title",
                    type_=sa.String(length=255), existing_type=sa.Text(),
                    existing_nullable=True)
