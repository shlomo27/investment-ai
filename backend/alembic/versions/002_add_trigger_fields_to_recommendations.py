"""Add trigger_type and trigger_details to recommendations

Revision ID: 002
Revises: 001
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recommendations",
        sa.Column("trigger_type", sa.String(50), nullable=True, server_default="SCHEDULED"),
    )
    op.add_column(
        "recommendations",
        sa.Column("trigger_details", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("recommendations", "trigger_details")
    op.drop_column("recommendations", "trigger_type")
