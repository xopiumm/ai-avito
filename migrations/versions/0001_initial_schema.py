"""Initial schema creation for Weather Alerts.

Creates base tables:
- locations: normalized weather data locations
- subscriptions: user alert subscriptions per location
- subscription_conditions: weather conditions triggering alerts
- delivery_channels: notification delivery destinations

Revision ID: 0001
Revises: 
Create Date: 2026-04-09 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial schema."""

    # ========================================================================
    # Create locations table (referenced by subscriptions)
    # ========================================================================
    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_location_key", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("timezone", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_locations")),
        sa.UniqueConstraint(
            "provider_location_key",
            name=op.f("uq_locations_provider_location_key"),
        ),
    )
    op.create_index(op.f("ix_locations_timezone"), "locations", ["timezone"])

    # ========================================================================
    # Create subscriptions table
    # ========================================================================
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "disabled", "deleted", name="subscriptionstatus"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("condition_mode", sa.String(length=10), nullable=False, server_default="ANY"),
        sa.Column(
            "schedule_timezone_source",
            sa.String(length=20),
            nullable=False,
            server_default="location",
        ),
        sa.Column("active_from", sa.String(length=5), nullable=True),
        sa.Column("active_to", sa.String(length=5), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], name=op.f("fk_subscriptions_location_id")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscriptions")),
        sa.UniqueConstraint(
            "user_id",
            "location_id",
            "status",
            name=op.f("uq_user_location_active_status"),
            sqlite_where="status != 'deleted'",
        ),
    )
    op.create_index(op.f("ix_subscriptions_location_id"), "subscriptions", ["location_id"])
    op.create_index(op.f("ix_subscriptions_status"), "subscriptions", ["status"])
    op.create_index(op.f("ix_subscriptions_user_id"), "subscriptions", ["user_id"])

    # ========================================================================
    # Create subscription_conditions table
    # ========================================================================
    op.create_table(
        "subscription_conditions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "temperature_below",
                "temperature_above",
                "rain_probability_above",
                "wind_speed_above",
                "severe_weather",
                name="conditiontype",
            ),
            nullable=False,
        ),
        sa.Column("threshold_value", sa.Float(), nullable=True),
        sa.Column("threshold_unit", sa.String(length=20), nullable=True),
        sa.Column(
            "severity_event_type",
            sa.Enum(
                "storm",
                "hurricane",
                "tornado",
                "blizzard",
                "extreme_heat",
                "extreme_cold",
                name="severityeventtype",
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "NOT (type IN ('temperature_below', 'temperature_above', 'rain_probability_above', 'wind_speed_above') AND threshold_value IS NULL)",
            name="ck_numeric_condition_needs_threshold",
        ),
        sa.CheckConstraint(
            "NOT (type = 'severe_weather' AND severity_event_type IS NULL)",
            name="ck_severe_weather_needs_type",
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["subscriptions.id"],
            name=op.f("fk_subscription_conditions_subscription_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscription_conditions")),
    )
    op.create_index(
        op.f("ix_subscription_conditions_subscription_id"),
        "subscription_conditions",
        ["subscription_id"],
    )
    op.create_index(op.f("ix_subscription_conditions_type"), "subscription_conditions", ["type"])

    # ========================================================================
    # Create delivery_channels table
    # ========================================================================
    op.create_table(
        "delivery_channels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column(
            "type",
            sa.Enum("email", "push", "webhook", name="deliverychanneltype"),
            nullable=False,
        ),
        sa.Column("destination", sa.String(length=500), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "failure_state",
            sa.Enum("ok", "failed", "retrying", name="failurestate"),
            nullable=False,
            server_default="ok",
        ),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["subscriptions.id"],
            name=op.f("fk_delivery_channels_subscription_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_delivery_channels")),
    )
    op.create_index(
        op.f("ix_delivery_channels_subscription_id"),
        "delivery_channels",
        ["subscription_id"],
    )
    op.create_index(op.f("ix_delivery_channels_type"), "delivery_channels", ["type"])
    op.create_index(op.f("ix_delivery_channels_active"), "delivery_channels", ["active"])
    op.create_index(
        op.f("ix_delivery_channels_failure_state"),
        "delivery_channels",
        ["failure_state"],
    )


def downgrade() -> None:
    """Drop all created tables."""

    # Drop enum types (if using PostgreSQL)
    op.execute("DROP TABLE IF EXISTS delivery_channels CASCADE")
    op.execute("DROP TABLE IF EXISTS subscription_conditions CASCADE")
    op.execute("DROP TABLE IF EXISTS subscriptions CASCADE")
    op.execute("DROP TABLE IF EXISTS locations CASCADE")

    # Drop enums (PostgreSQL specific)
    op.execute("DROP TYPE IF EXISTS deliverychanneltype CASCADE")
    op.execute("DROP TYPE IF EXISTS failurestate CASCADE")
    op.execute("DROP TYPE IF EXISTS severityeventtype CASCADE")
    op.execute("DROP TYPE IF EXISTS conditiontype CASCADE")
    op.execute("DROP TYPE IF EXISTS subscriptionstatus CASCADE")
