"""API routes for Weather Alerts."""

from .subscriptions import router as subscriptions_router

__all__ = [
    "subscriptions_router",
]
