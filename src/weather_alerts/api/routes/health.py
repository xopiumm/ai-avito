"""Health check routes for API readiness and dependency status.

Provides endpoints for monitoring the health of the Weather Alerts API and
its dependencies (PostgreSQL, Redis, Celery).

Endpoints:
  GET /health - Health status with detailed component diagnostics
"""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import APIRouter, status as http_status
from pydantic import BaseModel
from sqlalchemy import text

from src.weather_alerts.config.database import get_engine, get_session_factory
from src.weather_alerts.config.redis import ping_redis, get_redis_client
from src.weather_alerts.config.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["system"])


# ============================================================================
# RESPONSE MODELS
# ============================================================================


class ComponentHealth(BaseModel):
    """Health status of a single component."""
    
    status: str  # "healthy", "degraded", "unhealthy"
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    """Overall health status response."""
    
    status: str  # "healthy", "degraded", "unhealthy"
    timestamp: str  # ISO format
    uptime_seconds: Optional[float] = None
    components: Dict[str, ComponentHealth]


# ============================================================================
# GLOBAL STATE
# ============================================================================

_startup_time: Optional[float] = None


def set_startup_time(timestamp: float) -> None:
    """Set application startup time. Called from main.py on startup."""
    global _startup_time
    _startup_time = timestamp


def get_uptime_seconds() -> float:
    """Get application uptime in seconds since startup."""
    if _startup_time is None:
        return 0.0
    return time.time() - _startup_time


# ============================================================================
# HEALTH CHECK FUNCTIONS
# ============================================================================


async def check_database() -> ComponentHealth:
    """Check PostgreSQL database connectivity.
    
    Attempts to acquire a connection from the pool and execute a simple query.
    
    Returns:
        ComponentHealth with status and diagnostics
    """
    start_time = time.time()
    try:
        engine = get_engine()
        
        # Test connection by executing a simple query (SQLAlchemy 2.x requires text() wrapper)
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            await result.scalar()
        
        latency = (time.time() - start_time) * 1000
        
        logger.debug(f"Database health check passed ({latency:.1f}ms)")
        
        return ComponentHealth(
            status="healthy",
            latency_ms=round(latency, 2),
            details={
                "pool_size": engine.pool.size(),
                "checked_out": engine.pool.checkedout(),
            }
        )
        
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        logger.warning(f"Database health check failed: {e}")
        return ComponentHealth(
            status="unhealthy",
            latency_ms=round(latency, 2),
            error=str(e),
        )


async def check_redis() -> ComponentHealth:
    """Check Redis connectivity.
    
    Uses PING command for a quick connectivity test.
    
    Returns:
        ComponentHealth with status
    """
    start_time = time.time()
    try:
        redis = await get_redis_client()
        result = await redis.ping()
        latency = (time.time() - start_time) * 1000
        
        if result is True:
            logger.debug(f"Redis health check passed ({latency:.1f}ms)")
            return ComponentHealth(
                status="healthy",
                latency_ms=round(latency, 2),
            )
        else:
            return ComponentHealth(
                status="unhealthy",
                latency_ms=round(latency, 2),
                error="PING returned unexpected response",
            )
            
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        logger.warning(f"Redis health check failed: {e}")
        return ComponentHealth(
            status="unhealthy",
            latency_ms=round(latency, 2),
            error=str(e),
        )


async def check_api() -> ComponentHealth:
    """Check API readiness.
    
    Quick check that the application is running and responsive.
    This is always "healthy" if we're able to execute this function.
    
    Returns:
        ComponentHealth with status
    """
    return ComponentHealth(
        status="healthy",
        latency_ms=0.1,
        details={
            "uptime_seconds": get_uptime_seconds(),
        }
    )


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.get(
    "/health",
    tags=["health"],
    summary="Health status with component diagnostics",
)
async def health_check() -> HealthResponse:
    """Health check endpoint with full component status.
    
    Performs health checks on all critical components:
    - API readiness
    - PostgreSQL database connectivity
    - Redis connectivity
    
    Used for:
    - Kubernetes liveness/readiness probes
    - Load balancers (ELB, ALB, etc.)
    - Debugging deployment issues
    - Monitoring dashboards
    
    Returns:
        HealthResponse with status of each component
        
    Response codes:
        200: API is healthy (may have degraded components)
        503: API is unhealthy (cannot serve requests)
    """
    logger.info("Health check requested")
    
    # Check all components in parallel
    import asyncio
    
    api_health = await check_api()
    db_health, redis_health = await asyncio.gather(
        check_database(),
        check_redis(),
    )
    
    components = {
        "api": api_health,
        "database": db_health,
        "redis": redis_health,
    }
    
    # Determine overall status
    # unhealthy: any component is unhealthy
    # degraded: any component is degraded (future use)
    # healthy: all components are healthy
    component_statuses = [c.status for c in components.values()]
    
    if "unhealthy" in component_statuses:
        overall_status = "unhealthy"
        response_code = http_status.HTTP_503_SERVICE_UNAVAILABLE
    elif "degraded" in component_statuses:
        overall_status = "degraded"
        response_code = http_status.HTTP_200_OK
    else:
        overall_status = "healthy"
        response_code = http_status.HTTP_200_OK
    
    response = HealthResponse(
        status=overall_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        uptime_seconds=get_uptime_seconds(),
        components={k: v for k, v in components.items()},
    )
    
    # Log the summary
    logger.info(
        "Health check completed",
        extra={
            "overall_status": overall_status,
            "api": api_health.status,
            "database": db_health.status,
            "redis": redis_health.status,
        }
    )
    
    # Custom response to return appropriate status code
    from fastapi import Response
    return Response(
        content=response.model_dump_json(),
        status_code=response_code,
        media_type="application/json",
    )
