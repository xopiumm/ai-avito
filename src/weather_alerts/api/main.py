"""FastAPI application factory and configuration.

Creates and configures the main FastAPI instance with:
- Routes registration
- Exception handlers
- Middleware
- Startup/shutdown events
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.weather_alerts.api.routes import subscriptions_router
from src.weather_alerts.config.database import close_db, init_db


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Includes:
    - Routes for subscription management
    - Exception handlers for service errors
    - Database initialization and cleanup
    - CORS middleware (future)

    Returns:
        Configured FastAPI instance ready for uvicorn
    """
    app = FastAPI(
        title="Weather Alerts API",
        description="Weather alerts subscription management service",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # ========================================================================
    # STARTUP/SHUTDOWN EVENTS
    # ========================================================================

    @app.on_event("startup")
    async def startup_event() -> None:
        """Initialize database on startup."""
        # Note: init_db creates tables (development only)
        # In production, use Alembic migrations
        await init_db()

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        """Clean up resources on shutdown."""
        await close_db()

    # ========================================================================
    # ROUTES
    # ========================================================================

    app.include_router(subscriptions_router)

    # ========================================================================
    # HEALTH CHECK
    # ========================================================================

    @app.get("/health", tags=["health"])
    async def health_check() -> dict:
        """Health check endpoint.

        Returns:
            Simple status dict
        """
        return {"status": "ok"}

    # ========================================================================
    # EXCEPTION HANDLERS
    # ========================================================================

    @app.exception_handler(Exception)
    async def general_exception_handler(request, exc: Exception):
        """Handle uncaught exceptions.

        Logs error and returns 500 Internal Server Error.
        """
        # TODO: Add proper logging
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    return app


# Application instance for uvicorn
app = create_app()

# For development: uvicorn src.weather_alerts.api.main:app --reload
