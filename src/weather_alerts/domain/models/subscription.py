"""ORM models for Weather Alerts subscriptions and related entities.

This module defines the core domain models using SQLAlchemy 2.0+:
- Subscription: User's weather alert configuration for a location
- SubscriptionCondition: Weather conditions that trigger notifications
- DeliveryChannel: Delivery destinations (email, push, webhook)
"""

from datetime import datetime
from enum import Enum as PyEnum
from typing import List

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.weather_alerts.config import Base


# ============================================================================
# ENUMS
# ============================================================================


class SubscriptionStatus(str, PyEnum):
    """Subscription lifecycle statuses."""

    ACTIVE = "active"
    DISABLED = "disabled"
    DELETED = "deleted"


class ConditionType(str, PyEnum):
    """Weather condition types that can trigger notifications."""

    TEMPERATURE_BELOW = "temperature_below"
    TEMPERATURE_ABOVE = "temperature_above"
    RAIN_PROBABILITY_ABOVE = "rain_probability_above"
    WIND_SPEED_ABOVE = "wind_speed_above"
    SEVERE_WEATHER = "severe_weather"


class SeverityEventType(str, PyEnum):
    """Types of severe weather events."""

    STORM = "storm"
    HURRICANE = "hurricane"
    TORNADO = "tornado"
    BLIZZARD = "blizzard"
    EXTREME_HEAT = "extreme_heat"
    EXTREME_COLD = "extreme_cold"


class DeliveryChannelType(str, PyEnum):
    """Supported delivery channels."""

    EMAIL = "email"
    PUSH = "push"
    WEBHOOK = "webhook"


class FailureState(str, PyEnum):
    """Delivery channel failure states."""

    OK = "ok"
    FAILED = "failed"
    RETRYING = "retrying"


# ============================================================================
# ORM MODELS
# ============================================================================


class Subscription(Base):
    """Weather alerts subscription for a user and location.

    Represents a single user's notification configuration for weather conditions
    at a specific location. Multiple subscriptions can exist per user on different
    locations with different conditions.

    Attributes:
        id: Primary key, auto-incremented
        user_id: External user identifier (string, managed in external system)
        location_id: Foreign key to location
        status: Subscription state (active, disabled, deleted)
        condition_mode: Currently only "ANY" supported (any condition triggers)
        schedule_timezone_source: Source of timezone for schedule window (e.g., "location")
        active_from: Start time for delivery window (HH:MM format, e.g., "08:00")
        active_to: End time for delivery window (HH:MM format, e.g., "20:00")
        created_at: Subscription creation timestamp
        updated_at: Last modification timestamp
        deleted_at: Soft delete timestamp (if status=deleted)

    Relationships:
        conditions: List of weather conditions that trigger notifications
        channels: List of delivery channels (email, push, webhook)
    """

    __tablename__ = "subscriptions"
    __table_args__ = (
        # Composite unique constraint per user+location+status combination
        # Allows multiple subscriptions per location if some are deleted
        UniqueConstraint(
            "user_id",
            "location_id",
            "status",
            name="uq_user_location_active_status",
        ),
    )

    # Primary Key
    id: Mapped[int] = mapped_column(primary_key=True)

    # Foreign Keys & User Id
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False, index=True)

    # Status & Configuration
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus),
        default=SubscriptionStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    condition_mode: Mapped[str] = mapped_column(
        String(10),
        default="ANY",
        nullable=False,
        comment="Only 'ANY' supported: any condition triggers notification",
    )
    schedule_timezone_source: Mapped[str] = mapped_column(
        String(20),
        default="location",
        nullable=False,
        comment="Source of timezone for schedule window (location or user)",
    )

    # Delivery Window (local time at location/user timezone)
    active_from: Mapped[str] = mapped_column(
        String(5),  # HH:MM format
        nullable=True,
        comment="Delivery window start time (HH:MM), null = no restriction",
    )
    active_to: Mapped[str] = mapped_column(
        String(5),  # HH:MM format
        nullable=True,
        comment="Delivery window end time (HH:MM), null = no restriction",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Soft delete timestamp; used when status=deleted",
    )

    # Relationships
    conditions: Mapped[List["SubscriptionCondition"]] = relationship(
        "SubscriptionCondition",
        back_populates="subscription",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    channels: Mapped[List["DeliveryChannel"]] = relationship(
        "DeliveryChannel",
        back_populates="subscription",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<Subscription id={self.id} user_id={self.user_id} "
            f"location_id={self.location_id} status={self.status}>"
        )


class SubscriptionCondition(Base):
    """Weather condition that triggers a notification.

    Represents a single weather condition within a subscription.
    Multiple conditions use ANY logic: if any condition matches, notification triggers.

    Attributes:
        id: Primary key, auto-incremented
        subscription_id: Foreign key to subscription
        type: Weather condition type (temperature_below, rain_probability_above, etc.)
        threshold_value: Numeric threshold for the condition (e.g., -10 for temp, 70 for rain%)
        threshold_unit: Unit for threshold (e.g., "C" for temperature, "%" for rain)
        severity_event_type: For severe_weather type, specifies which events (storm, hurricane, etc.)
        created_at: Creation timestamp (immutable)

    Relationships:
        subscription: Parent subscription
    """

    __tablename__ = "subscription_conditions"

    # Primary Key
    id: Mapped[int] = mapped_column(primary_key=True)

    # Foreign Key
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id"),
        nullable=False,
        index=True,
    )

    # Condition Type & Threshold
    type: Mapped[ConditionType] = mapped_column(
        Enum(ConditionType),
        nullable=False,
        index=True,
    )
    threshold_value: Mapped[float] = mapped_column(
        nullable=True,
        comment="Numeric threshold for temperature, rain%, wind speed, etc. (null for severe_weather)",
    )
    threshold_unit: Mapped[str] = mapped_column(
        String(20),
        nullable=True,
        comment="Unit for threshold_value (C, F, %, km/h, etc.)",
    )

    # Severe Weather Specification
    severity_event_type: Mapped[SeverityEventType] = mapped_column(
        Enum(SeverityEventType),
        nullable=True,
        comment="For type=severe_weather, which event: storm, hurricane, tornado, etc.",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    subscription: Mapped["Subscription"] = relationship(
        "Subscription",
        back_populates="conditions",
        foreign_keys=[subscription_id],
    )

    __table_args__ = (
        # Constraint: for numeric conditions, threshold_value must be set
        CheckConstraint(
            "NOT (type IN ('temperature_below', 'temperature_above', 'rain_probability_above', 'wind_speed_above') AND threshold_value IS NULL)",
            name="ck_numeric_condition_needs_threshold",
        ),
        # Constraint: for severe_weather, severity_event_type must be set
        CheckConstraint(
            "NOT (type = 'severe_weather' AND severity_event_type IS NULL)",
            name="ck_severe_weather_needs_type",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<SubscriptionCondition id={self.id} subscription_id={self.subscription_id} "
            f"type={self.type} threshold={self.threshold_value}{self.threshold_unit}>"
        )


class DeliveryChannel(Base):
    """Delivery channel for notifications (email, push, webhook).

    Represents a destination for sending weather alert notifications.
    A subscription must have at least one active delivery channel.

    Attributes:
        id: Primary key, auto-incremented
        subscription_id: Foreign key to subscription
        type: Channel type (email, push, webhook)
        destination: Channel-specific address:
            - For email: email address
            - For push: device token or user device ID
            - For webhook: callback URL
        active: Whether this channel is currently enabled for delivery
        failure_state: Current failure state (ok, failed, retrying)
        retry_count: Number of failed delivery attempts (reset after success)
        last_failure_at: Timestamp of most recent failure
        created_at: Channel creation timestamp
        updated_at: Last modification timestamp

    Relationships:
        subscription: Parent subscription
    """

    __tablename__ = "delivery_channels"

    # Primary Key
    id: Mapped[int] = mapped_column(primary_key=True)

    # Foreign Key
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id"),
        nullable=False,
        index=True,
    )

    # Channel Configuration
    type: Mapped[DeliveryChannelType] = mapped_column(
        Enum(DeliveryChannelType),
        nullable=False,
        index=True,
    )
    destination: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Email address, device token, or webhook URL",
    )

    # Channel State
    active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        index=True,
        comment="Whether notifications are sent to this channel",
    )
    failure_state: Mapped[FailureState] = mapped_column(
        Enum(FailureState),
        default=FailureState.OK,
        nullable=False,
        index=True,
        comment="Current delivery status (ok, failed, retrying)",
    )
    retry_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
        comment="Number of consecutive failed delivery attempts",
    )
    last_failure_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of most recent delivery failure",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    subscription: Mapped["Subscription"] = relationship(
        "Subscription",
        back_populates="channels",
        foreign_keys=[subscription_id],
    )

    def __repr__(self) -> str:
        return (
            f"<DeliveryChannel id={self.id} subscription_id={self.subscription_id} "
            f"type={self.type} active={self.active} state={self.failure_state}>"
        )
