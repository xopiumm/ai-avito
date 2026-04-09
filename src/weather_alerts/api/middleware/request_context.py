"""Request context middleware for FastAPI.

Provides middleware that:
- Generates or extracts correlation IDs from X-Correlation-ID header
- Stores correlation ID in async context for logging propagation
- Sets request path context for log enrichment
- Handles request/response timing and error tracking
- Integrates with structured logging

Correlation ID flow:
1. Request arrives with optional X-Correlation-ID header
2. If not present, generate UUID
3. Store in context (correlates all logs for this request)
4. Include in response header for client tracking
5. On error, correlate logs with request

Integration with logging:
    All loggers created via get_logger() automatically include correlation_id
    in their JSON output, without explicit parameter passing.
    
Integration with Celery tasks:
    Middleware stores correlation_id in request state, which can be passed
    to task with apply_async().
    
Usage in main.py:
    app = create_app()
    app.add_middleware(RequestContextMiddleware)
"""

import uuid
import time
import logging
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from src.weather_alerts.config.logging import (
    set_correlation_id,
    set_user_id,
    set_request_path,
    clear_context,
    get_logger,
)

logger = get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """HTTP middleware for request context management.
    
    Sets up async context variables (correlation_id, user_id, request_path)
    for the duration of the request. These are automatically included in
    all structured logs for correlation and tracing.
    
    Features:
    - Generates unique correlation ID per request (or extracts from header)
    - Stores in context for async propagation to workers/services
    - Tracks request duration and status
    - Handles cleanup on completion or error
    - Returns correlation ID in response header
    """
    
    # Header names (can be overridden in config)
    CORRELATION_ID_HEADER = "X-Correlation-ID"
    REQUEST_ID_HEADER = "X-Request-ID"  # Alias for compatibility
    USER_ID_HEADER = "X-User-ID"
    SOURCE_HEADER = "X-Source"
    
    def __init__(self, app: ASGIApp):
        """Initialize middleware.
        
        Args:
            app: ASGI application to wrap
        """
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and manage context.
        
        Args:
            request: Incoming HTTP request
            call_next: ASGI next middleware/route handler
            
        Returns:
            HTTP response with correlation ID header
        """
        # Extract or generate correlation ID
        correlation_id = (
            request.headers.get(self.CORRELATION_ID_HEADER) or
            request.headers.get(self.REQUEST_ID_HEADER) or
            str(uuid.uuid4())
        )
        
        # Extract user ID from header (if auth provides it)
        user_id = request.headers.get(self.USER_ID_HEADER)
        
        # Store request path
        request_path = request.url.path
        source = request.headers.get(self.SOURCE_HEADER, "api")
        
        # Initialize response to None (call_next may raise before assignment)
        response: Optional[Response] = None
        start_time = time.time()
        
        try:
            # Set context variables (available to all async operations in this request)
            set_correlation_id(correlation_id)
            if user_id:
                set_user_id(user_id)
            set_request_path(request_path)
            
            # Store correlation ID in request state for later use (e.g., in route handlers)
            request.state.correlation_id = correlation_id
            request.state.user_id = user_id
            request.state.source = source
            
            logger.debug(
                "Request started",
                extra={
                    "method": request.method,
                    "path": request_path,
                    "client_host": request.client.host if request.client else "unknown",
                },
            )
            
            # Call next middleware/handler
            response: Response = await call_next(request)
            
            # Track duration and success
            duration_ms = (time.time() - start_time) * 1000
            logger.info(
                "Request completed",
                extra={
                    "method": request.method,
                    "path": request_path,
                    "status": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            
        except Exception as e:
            # Log request error with correlation context
            duration_ms = (time.time() - start_time) * 1000
            logger.exception(
                "Request failed",
                extra={
                    "method": request.method,
                    "path": request_path,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            raise
            
        finally:
            # Add correlation ID to response headers for client tracking (only if response exists)
            if response is not None:
                response.headers[self.CORRELATION_ID_HEADER] = correlation_id
                
                # Optional: Include in response body for client convenience
                # response.headers["X-Request-Duration-Ms"] = str(duration_ms)
            
            # Clear context to prevent leakage to next request
            clear_context()
        
        return response


class CeleryTaskContextMiddleware:
    """Context manager for Celery task correlation ID.
    
    Use this in Celery tasks to maintain correlation through the async task chain.
    
    Usage:
        from src.weather_alerts.config.logging import get_logger
        from src.weather_alerts.api.middleware.request_context import CeleryTaskContextMiddleware
        
        @app.task(bind=True)
        def send_notification(self, notification_id: str, correlation_id: str = None):
            with CeleryTaskContextMiddleware(correlation_id):
                logger.info("Processing notification", extra={"notification_id": notification_id})
    """
    
    def __init__(self, correlation_id: Optional[str] = None, user_id: Optional[str] = None):
        """Initialize Celery task context.
        
        Args:
            correlation_id: Unique request/task identifier (generates if not provided)
            user_id: Optional user identifier for logging context
        """
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.user_id = user_id
        self.previous_correlation_id = None
        self.previous_user_id = None
    
    def __enter__(self):
        """Enter context (set correlation ID)."""
        # Store previous values to restore after
        from src.weather_alerts.config.logging import get_correlation_id, get_user_id
        self.previous_correlation_id = get_correlation_id()
        self.previous_user_id = get_user_id()
        
        # Set new context
        set_correlation_id(self.correlation_id)
        if self.user_id:
            set_user_id(self.user_id)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context (restore previous correlation ID)."""
        # Restore or clear
        set_correlation_id(self.previous_correlation_id)
        if self.previous_user_id:
            set_user_id(self.previous_user_id)
        # No error suppression
        return False


def get_correlation_id_from_request(request: Request) -> str:
    """Extract correlation ID from request state.
    
    Convenience function for route handlers to access the correlation ID.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Correlation ID set by middleware
        
    Example:
        @router.get("/subscriptions/{id}")
        async def get_subscription(id: str, request: Request):
            correlation_id = get_correlation_id_from_request(request)
            logger.info("Fetching subscription", extra={"correlation_id": correlation_id})
    """
    return getattr(request.state, "correlation_id", None)


def get_user_id_from_request(request: Request) -> Optional[str]:
    """Extract user ID from request state.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        User ID if provided in X-User-ID header, None otherwise
    """
    return getattr(request.state, "user_id", None)


def set_task_correlation_id(correlation_id: str) -> None:
    """Set correlation ID from request for passing to background tasks.
    
    Use this in route handlers before submitting tasks to ensure task retains
    the same correlation ID for end-to-end tracing.
    
    Args:
        correlation_id: The correlation ID to propagate to background task
        
    Example:
        @router.post("/subscriptions/")
        async def create_subscription(subscription: SubscriptionCreate, request: Request):
            correlation_id = get_correlation_id_from_request(request)
            
            # Submit background task with correlation_id
            from src.weather_alerts.workers import submit_delivery_task
            submit_delivery_task(
                ...
                metadata={"correlation_id": correlation_id}
            )
    """
    from src.weather_alerts.config.logging import set_correlation_id
    set_correlation_id(correlation_id)
