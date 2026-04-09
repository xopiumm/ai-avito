"""Business logic services for Weather Alerts.

This package contains the service layer, implementing business logic
for domain operations:
- SubscriptionService: Subscription lifecycle management
- ConditionEvaluationService: Weather condition evaluation
- Other services: Weather evaluation, delivery, etc. (to be implemented)

Services use domain exceptions (not HTTP) for proper layering.

Services are imported on-demand to avoid circular dependencies:
    from src.weather_alerts.services.subscription_service import SubscriptionService
    from src.weather_alerts.services.condition_evaluation_service import (
        ConditionEvaluationService,
        ConditionEvaluationResult,
        MatchedCondition,
        EventType,
    )
"""

from .exceptions import (
    ConditionEvaluationError,
    ConditionEvaluationException,
    EmptyConditionSet,
    InvalidSubscriptionData,
    InvalidWeatherData,
    LocationNotFound,
    SubscriptionAlreadyActive,
    SubscriptionAlreadyDeleted,
    SubscriptionAlreadyDisabled,
    SubscriptionAlreadyExists,
    SubscriptionNotFound,
    UnauthorizedSubscriptionAccess,
    WeatherAlertsException,
)

__all__ = [
    # Service classes - import on-demand to avoid circular dependencies
    # "SubscriptionService",
    # "ConditionEvaluationService",
    # "ConditionEvaluationResult",
    # "MatchedCondition",
    # "EventType",
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
    # Condition evaluation exceptions
    "ConditionEvaluationException",
    "InvalidWeatherData",
    "EmptyConditionSet",
    "ConditionEvaluationError",
]
