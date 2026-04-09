"""API schemas for request/response serialization.

This module contains Pydantic v2 schemas for all Weather Alerts API endpoints,
including request models, response models, and nested schemas for subscriptions,
conditions, and delivery channels.
"""

from .subscription import (
    ConditionTypeEnum,
    CreateSubscriptionRequest,
    DeliveryChannelCreateSchema,
    DeliveryChannelResponseSchema,
    DeliveryChannelTypeEnum,
    ErrorDetail,
    ErrorResponse,
    LocationSchema,
    ScheduleSchema,
    SeverityEventTypeEnum,
    SubscriptionConditionCreateSchema,
    SubscriptionConditionResponseSchema,
    SubscriptionListItem,
    SubscriptionResponse,
    SubscriptionStatusEnum,
    UpdateSubscriptionRequest,
)

__all__ = [
    "ConditionTypeEnum",
    "CreateSubscriptionRequest",
    "DeliveryChannelCreateSchema",
    "DeliveryChannelResponseSchema",
    "DeliveryChannelTypeEnum",
    "ErrorDetail",
    "ErrorResponse",
    "LocationSchema",
    "ScheduleSchema",
    "SeverityEventTypeEnum",
    "SubscriptionConditionCreateSchema",
    "SubscriptionConditionResponseSchema",
    "SubscriptionListItem",
    "SubscriptionResponse",
    "SubscriptionStatusEnum",
    "UpdateSubscriptionRequest",
]
