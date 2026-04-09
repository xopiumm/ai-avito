"""Domain-level exceptions for Weather Alerts services.

These exceptions represent business logic failures and should NOT be mapped
directly to HTTP status codes (that's the API layer's responsibility).
"""


class WeatherAlertsException(Exception):
    """Base exception for Weather Alerts service."""

    pass


class SubscriptionNotFound(WeatherAlertsException):
    """Subscription does not exist or belongs to different user."""

    pass


class SubscriptionAlreadyExists(WeatherAlertsException):
    """Subscription already exists for this user/location/status combination."""

    pass


class SubscriptionAlreadyDeleted(WeatherAlertsException):
    """Subscription is already in deleted status."""

    pass


class SubscriptionAlreadyDisabled(WeatherAlertsException):
    """Subscription is already in disabled status."""

    pass


class SubscriptionAlreadyActive(WeatherAlertsException):
    """Subscription is already in active status."""

    pass


class LocationNotFound(WeatherAlertsException):
    """Location does not exist or is invalid."""

    pass


class InvalidSubscriptionData(WeatherAlertsException):
    """Subscription data violates business rules or validation."""

    pass


class UnauthorizedSubscriptionAccess(WeatherAlertsException):
    """User is not authorized to access this subscription."""

    pass
