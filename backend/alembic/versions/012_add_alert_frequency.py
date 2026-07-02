"""Add alert frequency preference to users

Revision ID: 012
Revises: 011
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("alert_frequency", sa.String(20), nullable=False, server_default="REALTIME"),
    )
    op.add_column(
        "users",
        sa.Column("last_digest_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "last_digest_sent_at")
    op.drop_column("users", "alert_frequency")
