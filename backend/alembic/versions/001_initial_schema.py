"""Initial database schema

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column(
            "risk_profile",
            sa.Enum("CONSERVATIVE", "PASSIVE", "AGGRESSIVE", "HYBRID", name="riskprofile"),
            nullable=False,
            server_default="PASSIVE",
        ),
        sa.Column("risk_score", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("cash_balance", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("max_single_asset_exposure", sa.Float(), nullable=False, server_default="0.03"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_onboarded", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("preferred_language", sa.String(10), nullable=False, server_default="he"),
        sa.Column("push_token", sa.String(512), nullable=True),
        sa.Column("notification_email", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notification_sms", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notification_push", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # assets table
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_hebrew", sa.String(255), nullable=True),
        sa.Column(
            "exchange",
            sa.Enum("NASDAQ", "NYSE", "TASE", "AMEX", "LSE", "EURONEXT", "OTHER", name="exchange"),
            nullable=False,
            server_default="NASDAQ",
        ),
        sa.Column(
            "asset_type",
            sa.Enum("STOCK", "ETF", "BOND", "CRYPTO", "COMMODITY", name="assettype"),
            nullable=False,
            server_default="STOCK",
        ),
        sa.Column("is_active_in_pool", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "risk_level",
            sa.Enum("LOW", "MEDIUM", "HIGH", "VERY_HIGH", name="risklevel"),
            nullable=False,
            server_default="MEDIUM",
        ),
        sa.Column("sector", sa.String(100), nullable=True),
        sa.Column("country", sa.String(50), nullable=False, server_default="US"),
        sa.Column("last_price", sa.Float(), nullable=True),
        sa.Column("market_cap", sa.Float(), nullable=True),
        sa.Column("pe_ratio", sa.Float(), nullable=True),
        sa.Column("dividend_yield", sa.Float(), nullable=True),
        sa.Column("beta", sa.Float(), nullable=True),
        sa.Column("sentiment_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("fundamental_score", sa.Float(), nullable=False, server_default="50.0"),
        sa.Column("technical_score", sa.Float(), nullable=True),
        sa.Column("last_analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("added_to_pool_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("removed_from_pool_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assets_id", "assets", ["id"])
    op.create_index("ix_assets_symbol", "assets", ["symbol"], unique=True)
    op.create_index("ix_assets_is_active_in_pool", "assets", ["is_active_in_pool"])

    # portfolios table
    op.create_table(
        "portfolios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("avg_buy_price", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("current_price", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("current_value", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("pnl", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("pnl_percentage", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("exposure_percentage", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_portfolios_id", "portfolios", ["id"])
    op.create_index("ix_portfolios_user_id", "portfolios", ["user_id"])
    op.create_index("ix_portfolios_symbol", "portfolios", ["symbol"])

    # recommendations table
    op.create_table(
        "recommendations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column(
            "recommendation_type",
            sa.Enum("BUY", "SELL", "HOLD", "STRONG_BUY", "STRONG_SELL", name="recommendationtype"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING_SENIOR_REVIEW", "APPROVED", "REJECTED",
                "PRESENTED_TO_USER", "ACTIONED", "DISMISSED",
                name="recommendationstatus",
            ),
            nullable=False,
            server_default="PENDING_SENIOR_REVIEW",
        ),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("target_price", sa.Float(), nullable=True),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("current_price_at_recommendation", sa.Float(), nullable=True),
        sa.Column("data_fetcher_raw", sa.JSON(), nullable=True),
        sa.Column("fundamental_analysis", sa.JSON(), nullable=True),
        sa.Column("fundamental_notes", sa.Text(), nullable=True),
        sa.Column("sentiment_data", sa.JSON(), nullable=True),
        sa.Column("senior_review_notes", sa.Text(), nullable=True),
        sa.Column("senior_notes", sa.Text(), nullable=True),
        sa.Column("senior_approved_by", sa.String(100), nullable=True),
        sa.Column("technical_analysis", sa.JSON(), nullable=True),
        sa.Column("technical_notes", sa.Text(), nullable=True),
        sa.Column("risk_factors", sa.JSON(), nullable=True),
        sa.Column("expected_return_pct", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("presented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actioned_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recommendations_id", "recommendations", ["id"])
    op.create_index("ix_recommendations_asset_id", "recommendations", ["asset_id"])
    op.create_index("ix_recommendations_symbol", "recommendations", ["symbol"])

    # orders table
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("recommendation_id", sa.Integer(), nullable=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column(
            "order_type",
            sa.Enum("BUY", "SELL", name="ordertype"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("PENDING", "EXECUTED", "CANCELLED", "REJECTED", "PARTIALLY_FILLED", name="orderstatus"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("price_at_order", sa.Float(), nullable=False),
        sa.Column("executed_price", sa.Float(), nullable=True),
        sa.Column("total_amount", sa.Float(), nullable=False),
        sa.Column("executed_total", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recommendation_id"], ["recommendations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_orders_id", "orders", ["id"])
    op.create_index("ix_orders_user_id", "orders", ["user_id"])
    op.create_index("ix_orders_symbol", "orders", ["symbol"])

    # notifications table
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("recommendation_id", sa.Integer(), nullable=True),
        sa.Column(
            "notification_type",
            sa.Enum("RECOMMENDATION", "ALERT", "SYSTEM", "RISK_WARNING", "PRICE_TARGET", name="notificationtype"),
            nullable=False,
            server_default="RECOMMENDATION",
        ),
        sa.Column(
            "external_message",
            sa.Text(),
            nullable=False,
            server_default="יש לך עדכון השקעות חדש. אנא היכנס למערכת לצפייה בפרטים.",
        ),
        sa.Column("internal_detail", sa.JSON(), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("channels_sent", sa.JSON(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recommendation_id"], ["recommendations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_id", "notifications", ["id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_recommendation_id", "notifications", ["recommendation_id"])

    # watchlist table
    op.create_table(
        "watchlist",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("alert_on_technical_signal", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_technical_analysis", sa.JSON(), nullable=True),
        sa.Column("last_signal_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_watchlist_id", "watchlist", ["id"])
    op.create_index("ix_watchlist_user_id", "watchlist", ["user_id"])
    op.create_index("ix_watchlist_symbol", "watchlist", ["symbol"])

    # Seed initial asset pool with popular stocks
    op.execute("""
    INSERT INTO assets (symbol, name, exchange, asset_type, is_active_in_pool, risk_level, sector, country)
    VALUES
        ('AAPL', 'Apple Inc.', 'NASDAQ', 'STOCK', true, 'MEDIUM', 'Technology', 'US'),
        ('MSFT', 'Microsoft Corporation', 'NASDAQ', 'STOCK', true, 'LOW', 'Technology', 'US'),
        ('GOOGL', 'Alphabet Inc.', 'NASDAQ', 'STOCK', true, 'MEDIUM', 'Technology', 'US'),
        ('AMZN', 'Amazon.com Inc.', 'NASDAQ', 'STOCK', true, 'MEDIUM', 'Consumer Cyclical', 'US'),
        ('META', 'Meta Platforms Inc.', 'NASDAQ', 'STOCK', true, 'MEDIUM', 'Technology', 'US'),
        ('NVDA', 'NVIDIA Corporation', 'NASDAQ', 'STOCK', true, 'HIGH', 'Technology', 'US'),
        ('TSLA', 'Tesla Inc.', 'NASDAQ', 'STOCK', true, 'HIGH', 'Consumer Cyclical', 'US'),
        ('JPM', 'JPMorgan Chase & Co.', 'NYSE', 'STOCK', true, 'MEDIUM', 'Financial Services', 'US'),
        ('V', 'Visa Inc.', 'NYSE', 'STOCK', true, 'LOW', 'Financial Services', 'US'),
        ('JNJ', 'Johnson & Johnson', 'NYSE', 'STOCK', true, 'LOW', 'Healthcare', 'US'),
        ('NFLX', 'Netflix Inc.', 'NASDAQ', 'STOCK', true, 'HIGH', 'Communication Services', 'US'),
        ('AMD', 'Advanced Micro Devices', 'NASDAQ', 'STOCK', true, 'HIGH', 'Technology', 'US'),
        ('SPY', 'SPDR S&P 500 ETF', 'NYSE', 'ETF', true, 'LOW', 'Diversified', 'US'),
        ('QQQ', 'Invesco QQQ Trust', 'NASDAQ', 'ETF', true, 'MEDIUM', 'Technology', 'US')
    ON CONFLICT (symbol) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("watchlist")
    op.drop_table("notifications")
    op.drop_table("orders")
    op.drop_table("recommendations")
    op.drop_table("portfolios")
    op.drop_table("assets")
    op.drop_table("users")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS notificationtype")
    op.execute("DROP TYPE IF EXISTS orderstatus")
    op.execute("DROP TYPE IF EXISTS ordertype")
    op.execute("DROP TYPE IF EXISTS recommendationstatus")
    op.execute("DROP TYPE IF EXISTS recommendationtype")
    op.execute("DROP TYPE IF EXISTS risklevel")
    op.execute("DROP TYPE IF EXISTS assettype")
    op.execute("DROP TYPE IF EXISTS exchange")
    op.execute("DROP TYPE IF EXISTS riskprofile")
