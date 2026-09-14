"""Subscription tier, expiry and billing identity

The app is going to the stores as a consumer product with a free tier and a
paid one, so entitlements have to live on the account rather than being
implied by who was handed credentials.

Every existing account becomes FREE by default. The operator's own admin
account is unaffected in practice: entitlements_for() grants PRO to admins
regardless of tier, so nobody running the system locks themselves out.

Revision ID: 015
Revises: 014
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tier = sa.Enum("FREE", "PRO", name="subscriptiontier")
    source = sa.Enum("APPLE", "GOOGLE", "MANUAL", name="subscriptionsource")

    # create_type=False on the columns below would leave these undefined on
    # Postgres; create them explicitly so the migration is not order-dependent.
    bind = op.get_bind()
    tier.create(bind, checkfirst=True)
    source.create(bind, checkfirst=True)

    op.add_column(
        "users",
        sa.Column(
            "subscription_tier",
            tier,
            nullable=False,
            server_default="FREE",
        ),
    )
    op.add_column(
        "users",
        sa.Column("subscription_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("users", sa.Column("subscription_source", source, nullable=True))
    op.add_column(
        "users", sa.Column("billing_customer_id", sa.String(length=128), nullable=True)
    )
    op.create_index(
        "ix_users_billing_customer_id", "users", ["billing_customer_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_users_billing_customer_id", table_name="users")
    op.drop_column("users", "billing_customer_id")
    op.drop_column("users", "subscription_source")
    op.drop_column("users", "subscription_expires_at")
    op.drop_column("users", "subscription_tier")

    bind = op.get_bind()
    sa.Enum(name="subscriptionsource").drop(bind, checkfirst=True)
    sa.Enum(name="subscriptiontier").drop(bind, checkfirst=True)
