"""FastAPI application factory and configuration.

Creates and configures the main FastAPI instance with:
- Routes registration for subscription management
- Comprehensive exception handlers for domain and validation errors
- Database initialization and cleanup
- Request/response logging
- OpenAPI documentation

Architecture:
- Startup event: Initialize database connection
- Shutdown event: Close database connection and cleanup Redis
- Route registration: Include subscriptions router
- Exception handlers: Map domain exceptions to HTTP responses
- Middleware: Logging, CORS (future)

For development:
    $ uvicorn src.weather_alerts.api.main:app --reload
    $ open http://localhost:8000/docs

For production:
    Use Alembic migrations instead of init_db
    Enable proper logging with structured JSON logs
    Enable CORS with restricted origins
    Enable HTTPS
"""

import logging
from typing import Any, Dict

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.weather_alerts.api.routes import subscriptions_router
from src.weather_alerts.api.middleware.request_context import RequestContextMiddleware
from src.weather_alerts.config.database import close_db, init_db
from src.weather_alerts.config.logging import configure_logging, get_logger

# Logger for application events
logger = get_logger(__name__)


# ============================================================================
# ERROR RESPONSE MODELS
# ============================================================================


class ErrorResponse(dict):
    """Error response structure."""

    def __init__(self, status_code: int, detail: str, errors: list | None = None):
        """Initialize error response.

        Args:
            status_code: HTTP status code
            detail: Main error message
            errors: Optional list of field-level validation errors
        """
        super().__init__()
        self["status_code"] = status_code
        self["message"] = detail
        if errors:
            self["errors"] = errors


# ============================================================================
# APPLICATION FACTORY
# ============================================================================


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Factory function that initializes the FastAPI app instance with:
    1. OpenAPI documentation configuration
    2. Startup/shutdown event handlers
    3. Exception handlers for all error types
    4. Route registration
    5. Health check endpoint
    6. Structured logging and request context middleware

    Returns:
        Configured FastAPI instance ready for ASGI server
    """
    # Configure structured logging (must be done before creating app)
    configure_logging()
    
    app = FastAPI(
        title="Weather Alerts API",
        description="Weather alerts subscription management service. "
        "Enables users to create and manage weather-based notifications for specific locations.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # ====================================================================
    # MIDDLEWARE SETUP
    # ====================================================================
    # Request context middleware must be added BEFORE routes are defined
    # It manages correlation IDs and async context for logging
    app.add_middleware(RequestContextMiddleware)

    # ====================================================================
    # STARTUP/SHUTDOWN EVENTS
    # ====================================================================

    @app.on_event("startup")
    async def startup_event() -> None:
        """Initialize application resources on startup.

        Called once when ASGI server starts. Responsible for:
        1. Database connection setup
        2. Table creation (dev only, use Alembic in prod)
        3. Redis client initialization
        4. Configuration validation

        Errors during startup will prevent server from starting.
        """
        logger.info("Starting Weather Alerts API...")
        try:
            # Initialize database (creates tables if they don't exist)
            # In production, use Alembic migrations instead
            await init_db()
            logger.info("✓ Database initialized successfully")
        except Exception as e:
            logger.critical(f"✗ Database initialization failed: {e}")
            raise

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        """Clean up application resources on shutdown.

        Called once when ASGI server shuts down. Responsible for:
        1. Database session closure
        2. Redis connection cleanup
        3. Graceful task cancellation

        Must be idempotent - safe to call multiple times.
        """
        logger.info("Shutting down Weather Alerts API...")
        try:
            await close_db()
            logger.info("✓ Resources cleaned up successfully")
        except Exception as e:
            logger.warning(f"✗ Shutdown cleanup warning: {e}")
            # Don't raise during shutdown - best effort cleanup

    # ====================================================================
    # ROUTES
    # ====================================================================

    # Include subscription management router
    app.include_router(
        subscriptions_router,
        prefix="",  # Already prefixed in router as /alerts/subscriptions
    )

    # ====================================================================
    # SYSTEM ENDPOINTS
    # ====================================================================

    @app.get("/health", tags=["system"], summary="Health check")
    async def health_check() -> Dict[str, str]:
        """Health check endpoint for load balancers and monitoring.

        Simple endpoint that returns 200 if the service is running.
        Used by Kubernetes probes, load balancers, etc.

        Returns:
            {"status": "ok"} - Service is healthy
        """
        return {"status": "ok"}

    @app.get("/", tags=["system"], summary="API root")
    async def root() -> Dict[str, str]:
        """API root endpoint with basic information.

        Redirects to OpenAPI documentation.

        Returns:
            Message with documentation link
        """
        return {
            "message": "Weather Alerts API",
            "docs": "/docs",
            "redoc": "/redoc",
        }

    # ====================================================================
    # EXCEPTION HANDLERS
    # ====================================================================

    @app.exception_handler(RequestValidationError)
    async def pydantic_validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """Handle Pydantic validation errors from request bodies.

        Transforms Pydantic validation errors into readable error responses.

        Example error:
            {
                "status_code": 422,
                "message": "Invalid request data",
                "errors": [
                    {"field": "conditions", "issue": "at least 1 required"}
                ]
            }

        Args:
            request: Request that caused the error
            exc: Pydantic validation error

        Returns:
            JSON response with 422 Unprocessable Entity status
        """
        errors = []
        for error in exc.errors():
            field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
            errors.append(
                {
                    "field": field or "request",
                    "issue": error["msg"],
                    "type": error["type"],
                }
            )

        logger.warning(
            f"Validation error on {request.method} {request.url.path}: {len(errors)} errors"
        )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid request data",
                errors=errors,
            ),
        )

    @app.exception_handler(ValueError)
    async def value_error_exception_handler(
        request: Request,
        exc: ValueError,
    ) -> JSONResponse:
        """Handle ValueError exceptions.

        Maps caught ValueError to 400 Bad Request.

        Args:
            request: Request that caused the error
            exc: ValueError

        Returns:
            JSON response with 400 Bad Request status
        """
        logger.warning(f"Value error on {request.method} {request.url.path}: {exc}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ),
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Handle all uncaught exceptions.

        Last resort handler for any exception not caught by specific handlers.
        Returns 500 Internal Server Error without exposing implementation details.

        Args:
            request: Request that caused the error
            exc: Unhandled exception

        Returns:
            JSON response with 500 Internal Server Error status
        """
        logger.error(
            f"Unhandled exception on {request.method} {request.url.path}",
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error",
            ),
        )

    return app


# ============================================================================
# APPLICATION INSTANCE
# ============================================================================

# Create the main application instance
# This is imported and run by uvicorn
app = create_app()

# ============================================================================
# DEVELOPMENT RUNNING
# ============================================================================

# For development, run:
#   $ uvicorn src.weather_alerts.api.main:app --reload
#
# The --reload flag enables auto-reload on file changes
#
# For production, run with gunicorn/hypercorn:
#   $ gunicorn -w 4 -k uvicorn.workers.UvicornWorker \
#       src.weather_alerts.api.main:app
#
# Or with Docker:
#   $ docker-compose up
