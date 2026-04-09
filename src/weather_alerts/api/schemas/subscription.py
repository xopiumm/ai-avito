"""Pydantic v2 schemas for Weather Alerts subscription API.

Schemas for request/response serialization and validation.
"""

from datetime import datetime
from enum import Enum as PyEnum
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


# ============================================================================
# ENUMS FOR VALIDATION
# ============================================================================


class ConditionTypeEnum(str, PyEnum):
    """Supported weather condition types."""

    TEMPERATURE_BELOW = "temperature_below"
    TEMPERATURE_ABOVE = "temperature_above"
    RAIN_PROBABILITY_ABOVE = "rain_probability_above"
    WIND_SPEED_ABOVE = "wind_speed_above"
    SEVERE_WEATHER = "severe_weather"


class SeverityEventTypeEnum(str, PyEnum):
    """Supported severe weather event types."""

    STORM = "storm"
    HURRICANE = "hurricane"
    TORNADO = "tornado"
    BLIZZARD = "blizzard"
    EXTREME_HEAT = "extreme_heat"
    EXTREME_COLD = "extreme_cold"


class DeliveryChannelTypeEnum(str, PyEnum):
    """Supported delivery channel types."""

    EMAIL = "email"
    PUSH = "push"
    WEBHOOK = "webhook"


class SubscriptionStatusEnum(str, PyEnum):
    """Subscription status values."""

    ACTIVE = "active"
    DISABLED = "disabled"
    DELETED = "deleted"


# ============================================================================
# NESTED SCHEMAS
# ============================================================================


class LocationSchema(BaseModel):
    """Location reference for subscription."""

    id: int = Field(..., description="Location database ID")
    display_name: Optional[str] = Field(
        None, description="Location display name (human-readable)"
    )

    model_config = {"from_attributes": True}


class SubscriptionConditionCreateSchema(BaseModel):
    """Condition for subscription (create request)."""

    type: ConditionTypeEnum = Field(..., description="Weather condition type")
    threshold_value: Optional[float] = Field(
        None,
        description="Numeric threshold for temperature/rain/wind (required for non-severe types)",
    )
    threshold_unit: Optional[str] = Field(
        None,
        description="Unit of measurement (C, F, %, km/h). Auto-set based on type",
    )
    severity_event_type: Optional[SeverityEventTypeEnum] = Field(
        None,
        description="For type=severe_weather, which event. Required if type=severe_weather",
    )

    @field_validator("type")
    @classmethod
    def validate_condition_type(cls, v: ConditionTypeEnum) -> ConditionTypeEnum:
        """Ensure condition type is supported."""
        if v not in ConditionTypeEnum:
            raise ValueError(f"Unsupported condition type: {v}")
        return v

    @field_validator("threshold_value")
    @classmethod
    def validate_threshold_value(cls, v: Optional[float]) -> Optional[float]:
        """Validate threshold value is within reasonable ranges."""
        if v is not None:
            if not isinstance(v, (int, float)):
                raise ValueError("threshold_value must be numeric")
        return v

    @model_validator(mode="after")
    def validate_condition_requirements(self) -> "SubscriptionConditionCreateSchema":
        """Validate condition-type specific requirements."""
        numeric_types = {
            ConditionTypeEnum.TEMPERATURE_BELOW,
            ConditionTypeEnum.TEMPERATURE_ABOVE,
            ConditionTypeEnum.RAIN_PROBABILITY_ABOVE,
            ConditionTypeEnum.WIND_SPEED_ABOVE,
        }

        if self.type in numeric_types:
            if self.threshold_value is None:
                raise ValueError(
                    f"threshold_value is required for type={self.type}"
                )
            if self.severity_event_type is not None:
                raise ValueError(
                    f"severity_event_type should not be set for type={self.type}"
                )

        if self.type == ConditionTypeEnum.SEVERE_WEATHER:
            if self.severity_event_type is None:
                raise ValueError(
                    "severity_event_type is required for type=severe_weather"
                )
            if self.threshold_value is not None:
                raise ValueError(
                    "threshold_value should not be set for type=severe_weather"
                )

        return self


class SubscriptionConditionResponseSchema(SubscriptionConditionCreateSchema):
    """Condition response (includes ID)."""

    id: int = Field(..., description="Condition database ID")
    created_at: datetime = Field(..., description="Creation timestamp")

    model_config = {"from_attributes": True}


class DeliveryChannelCreateSchema(BaseModel):
    """Delivery channel configuration (create request)."""

    type: DeliveryChannelTypeEnum = Field(..., description="Channel type")
    destination: str = Field(..., description="Email address, device token, or webhook URL")
    active: bool = Field(
        default=True,
        description="Whether this channel is active for delivery",
    )

    @field_validator("type")
    @classmethod
    def validate_channel_type(
        cls, v: DeliveryChannelTypeEnum
    ) -> DeliveryChannelTypeEnum:
        """Ensure channel type is supported."""
        if v not in DeliveryChannelTypeEnum:
            raise ValueError(f"Unsupported channel type: {v}")
        return v

    @field_validator("destination")
    @classmethod
    def validate_destination(cls, v: str) -> str:
        """Validate destination format based on channel type."""
        if not v or not isinstance(v, str):
            raise ValueError("destination must be non-empty string")
        if len(v) > 500:
            raise ValueError("destination must be <= 500 characters")
        return v.strip()

    @model_validator(mode="after")
    def validate_destination_by_type(
        self,
    ) -> "DeliveryChannelCreateSchema":
        """Validate destination format matches channel type."""
        if self.type == DeliveryChannelTypeEnum.EMAIL:
            # Basic email validation
            if "@" not in self.destination or "." not in self.destination:
                raise ValueError(
                    f"Invalid email address: {self.destination}"
                )
        elif self.type == DeliveryChannelTypeEnum.WEBHOOK:
            # Basic URL validation
            if not self.destination.startswith(("http://", "https://")):
                raise ValueError(
                    f"Webhook URL must start with http:// or https://: {self.destination}"
                )
            if len(self.destination) < 10:
                raise ValueError("Webhook URL seems too short")

        return self


class DeliveryChannelResponseSchema(DeliveryChannelCreateSchema):
    """Delivery channel response (includes ID and state)."""

    id: int = Field(..., description="Channel database ID")
    failure_state: str = Field(
        default="ok",
        description="Current failure state (ok, failed, retrying)",
    )
    retry_count: int = Field(
        default=0,
        description="Number of consecutive failed attempts",
    )
    last_failure_at: Optional[datetime] = Field(
        None,
        description="Timestamp of most recent failure",
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last modification timestamp")

    model_config = {"from_attributes": True}


class ScheduleSchema(BaseModel):
    """Delivery schedule configuration."""

    timezone_source: Literal["location", "user"] = Field(
        default="location",
        description="Whether to use location or user's timezone",
    )
    active_from: Optional[str] = Field(
        None,
        description="Start of delivery window in HH:MM format (local timezone). None = no restriction",
    )
    active_to: Optional[str] = Field(
        None,
        description="End of delivery window in HH:MM format (local timezone). None = no restriction",
    )

    @field_validator("active_from", "active_to")
    @classmethod
    def validate_time_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate time is in HH:MM format."""
        if v is None:
            return v

        if not isinstance(v, str):
            raise ValueError("Time must be string in HH:MM format")

        parts = v.split(":")
        if len(parts) != 2:
            raise ValueError("Time must be in HH:MM format")

        try:
            hour = int(parts[0])
            minute = int(parts[1])

            if not (0 <= hour <= 23):
                raise ValueError("Hour must be 0-23")
            if not (0 <= minute <= 59):
                raise ValueError("Minute must be 0-59")
        except ValueError as e:
            raise ValueError(f"Invalid time format: {e}")

        return v.strip()

    @model_validator(mode="after")
    def validate_schedule_window(self) -> "ScheduleSchema":
        """Validate schedule window is valid."""
        if self.active_from and self.active_to:
            # Convert to comparable format
            from_parts = self.active_from.split(":")
            to_parts = self.active_to.split(":")

            from_mins = int(from_parts[0]) * 60 + int(from_parts[1])
            to_mins = int(to_parts[0]) * 60 + int(to_parts[1])

            if from_mins >= to_mins:
                raise ValueError(
                    "active_from must be before active_to (cross-midnight windows not supported)"
                )

        return self


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================


class CreateSubscriptionRequest(BaseModel):
    """Request schema for creating a subscription."""

    location: LocationSchema = Field(..., description="Location reference")
    conditions: List[SubscriptionConditionCreateSchema] = Field(
        ...,
        min_items=1,
        description="At least one condition required. ANY logic applies",
    )
    schedule: ScheduleSchema = Field(
        default_factory=ScheduleSchema,
        description="Delivery schedule window",
    )
    delivery_channels: List[DeliveryChannelCreateSchema] = Field(
        ...,
        min_items=1,
        description="At least one delivery channel required",
    )

    @field_validator("conditions")
    @classmethod
    def validate_conditions_not_empty(
        cls, v: List[SubscriptionConditionCreateSchema]
    ) -> List[SubscriptionConditionCreateSchema]:
        """Ensure at least one condition."""
        if not v:
            raise ValueError("At least one condition is required")
        return v

    @field_validator("delivery_channels")
    @classmethod
    def validate_channels_not_empty(
        cls, v: List[DeliveryChannelCreateSchema]
    ) -> List[DeliveryChannelCreateSchema]:
        """Ensure at least one delivery channel."""
        if not v:
            raise ValueError("At least one delivery channel is required")
        return v


class UpdateSubscriptionRequest(BaseModel):
    """Request schema for updating a subscription."""

    schedule: Optional[ScheduleSchema] = Field(
        None,
        description="Delivery schedule window (partial update)",
    )
    conditions: Optional[List[SubscriptionConditionCreateSchema]] = Field(
        None,
        min_items=1,
        description="New conditions (replaces existing)",
    )
    delivery_channels: Optional[List[DeliveryChannelCreateSchema]] = Field(
        None,
        min_items=1,
        description="New delivery channels (replaces existing)",
    )

    @field_validator("conditions")
    @classmethod
    def validate_conditions_if_provided(
        cls, v: Optional[List[SubscriptionConditionCreateSchema]]
    ) -> Optional[List[SubscriptionConditionCreateSchema]]:
        """Ensure conditions list is not empty if provided."""
        if v is not None and not v:
            raise ValueError("Conditions list must not be empty if provided")
        return v

    @field_validator("delivery_channels")
    @classmethod
    def validate_channels_if_provided(
        cls, v: Optional[List[DeliveryChannelCreateSchema]]
    ) -> Optional[List[DeliveryChannelCreateSchema]]:
        """Ensure channels list is not empty if provided."""
        if v is not None and not v:
            raise ValueError("Delivery channels list must not be empty if provided")
        return v


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================


class SubscriptionResponse(BaseModel):
    """Complete subscription response."""

    id: int = Field(..., description="Subscription database ID")
    user_id: str = Field(..., description="User identifier")
    location: LocationSchema = Field(..., description="Associated location")
    status: SubscriptionStatusEnum = Field(..., description="Subscription status")
    condition_mode: Literal["ANY"] = Field(..., description="Condition evaluation mode")
    schedule: ScheduleSchema = Field(..., description="Delivery schedule")
    conditions: List[SubscriptionConditionResponseSchema] = Field(
        ..., description="Weather conditions"
    )
    delivery_channels: List[DeliveryChannelResponseSchema] = Field(
        ..., description="Delivery channels"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last modification timestamp")
    deleted_at: Optional[datetime] = Field(
        None, description="Soft delete timestamp (if deleted)"
    )

    model_config = {"from_attributes": True}


class SubscriptionListItem(BaseModel):
    """Subscription item for list responses (summary view)."""

    id: int = Field(..., description="Subscription ID")
    user_id: str = Field(..., description="User identifier")
    location: LocationSchema = Field(..., description="Location")
    status: SubscriptionStatusEnum = Field(..., description="Status")
    conditions_count: int = Field(..., description="Number of conditions")
    channels_count: int = Field(..., description="Number of active channels")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last modification timestamp")

    model_config = {"from_attributes": True}


# ============================================================================
# ERROR RESPONSE SCHEMAS
# ============================================================================


class ErrorDetail(BaseModel):
    """Error detail in response."""

    field: Optional[str] = Field(None, description="Field name if validation error")
    message: str = Field(..., description="Error message")


class ErrorResponse(BaseModel):
    """Error response."""

    status_code: int = Field(..., description="HTTP status code")
    message: str = Field(..., description="Error message")
    details: Optional[List[ErrorDetail]] = Field(
        None, description="Detailed error information"
    )
