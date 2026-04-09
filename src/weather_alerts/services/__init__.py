"""Business logic services for Weather Alerts.

This package contains the service layer, implementing business logic
for domain operations:
- SubscriptionService: Subscription lifecycle management
- Other services: Weather evaluation, delivery, etc. (to be implemented)

Services use domain exceptions (not HTTP) for proper layering.
"""

from .exceptions import (
    InvalidSubscriptionData,
    LocationNotFound,
    SubscriptionAlreadyActive,
    SubscriptionAlreadyDeleted,
    SubscriptionAlreadyDisabled,
    SubscriptionAlreadyExists,
    SubscriptionNotFound,
    UnauthorizedSubscriptionAccess,
    WeatherAlertsException,
)
from .subscription_service import SubscriptionService

__all__ = [
    # Service classes
    "SubscriptionService",
    # Exceptions
    "WeatherAlertsException",
    "SubscriptionNotFound",
    "SubscriptionAlreadyExists",
    "SubscriptionAlreadyDeleted",
    "SubscriptionAlreadyDisabled",
    "SubscriptionAlreadyActive",
    "LocationNotFound",
    "InvalidSubscriptionData",
    "UnauthorizedSubscriptionAccess",
]
