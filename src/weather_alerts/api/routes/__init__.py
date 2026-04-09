"""API routes for Weather Alerts."""

from .subscriptions import router as subscriptions_router
from .health import router as health_router
from .metrics import router as metrics_router

__all__ = [
    "health_router",
    "metrics_router",
    "subscriptions_router",
]
