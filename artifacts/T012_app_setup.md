# T012: Advanced API Application Setup и Integration

**Date:** 2025-04-10  
**Task:** Complete application setup with error handling and local verification  
**Status:** ✅ Complete

## Overview

Реализована полная интеграция FastAPI приложения с единообразной обработкой ошибок, логированием, startup/shutdown wiring и готовностью к запуску на локальной машине.

## Files Created/Modified

### 1. `src/weather_alerts/api/main.py` (EXPANDED - 200+ lines)

Расширенная версия с полной функциональностью:

#### Application Factory

```python
def create_app() -> FastAPI:
    """Create and configure FastAPI application.
    
    Factory function that initializes:
    1. OpenAPI documentation config
    2. Startup/shutdown event handlers
    3. Exception handlers for all error types
    4. Route registration
    5. Health check endpoint
    """
    app = FastAPI(
        title="Weather Alerts API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
```

#### Startup Event (Development)

```python
@app.on_event("startup")
async def startup_event() -> None:
    """Initialize resources on startup.
    
    - Database connection setup
    - Table creation (dev only, use Alembic in prod)
    - Redis client initialization
    - Configuration validation
    
    Errors during startup prevent server from starting.
    """
    logger.info("Starting Weather Alerts API...")
    try:
        await init_db()
        logger.info("✓ Database initialized successfully")
    except Exception as e:
        logger.critical(f"✗ Database initialization failed: {e}")
        raise
```

#### Shutdown Event (Cleanup)

```python
@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Clean up resources on shutdown.
    
    - Database session closure
    - Redis connection cleanup
    - Graceful task cancellation
    
    Must be idempotent - safe to call multiple times.
    """
    logger.info("Shutting down Weather Alerts API...")
    try:
        await close_db()
        logger.info("✓ Resources cleaned up successfully")
    except Exception as e:
        logger.warning(f"✗ Shutdown cleanup warning: {e}")
        # Don't raise during shutdown - best effort
```

#### Routes Registration

```python
app.include_router(
    subscriptions_router,
    prefix="",  # Already prefixed in router
)
```

#### System Endpoints

```python
@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check for load balancers/monitoring.
    
    Used by Kubernetes probes, health monitors, etc.
    """
    return {"status": "ok"}

@app.get("/")
async def root() -> Dict[str, str]:
    """API root with documentation links."""
    return {
        "message": "Weather Alerts API",
        "docs": "/docs",
        "redoc": "/redoc",
    }
```

#### Exception Handlers (3 levels)

**1. Pydantic Validation Error Handler**
```python
@app.exception_handler(PydanticValidationError)
async def pydantic_validation_exception_handler(
    request: Request,
    exc: PydanticValidationError,
) -> JSONResponse:
    """Handle Pydantic validation errors from request bodies.
    
    Status: 422 Unprocessable Entity
    
    Example response:
    {
        "status_code": 422,
        "message": "Invalid request data",
        "errors": [
            {
                "field": "conditions",
                "issue": "at least 1 required",
                "type": "value_error"
            }
        ]
    }
    """
```

**2. Value Error Handler**
```python
@app.exception_handler(ValueError)
async def value_error_exception_handler(
    request: Request,
    exc: ValueError,
) -> JSONResponse:
    """Handle ValueError exceptions.
    
    Status: 400 Bad Request
    """
```

**3. General Exception Handler (Last Resort)**
```python
@app.exception_handler(Exception)
async def general_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Handle any uncaught exception.
    
    Status: 500 Internal Server Error
    
    Returns generic message without exposing implementation details.
    Logs full error with stack trace.
    """
```

#### Error Response Model

```python
class ErrorResponse(dict):
    """Standardized error response structure.
    
    Format:
    {
        "status_code": 400,
        "message": "Invalid request data",
        "errors": [
            {"field": "name", "issue": "required"}
        ]
    }
    """
```

### 2. `scripts/run_dev.sh` (80 lines)

Convenience script для запуска в режиме разработки:

```bash
#!/usr/bin/env bash
# Development server startup script

# Features:
✅ Virtual environment detection and activation
✅ Dependency installation check
✅ Docker-compose service startup (PostgreSQL, Redis)
✅ Colored console output
✅ Automatic uvicorn startup with --reload
✅ Documentation links output

Usage:
    $ chmod +x scripts/run_dev.sh
    $ ./scripts/run_dev.sh

Output:
    Weather Alerts API - Development Server
    =====================================
    
    ✓ Virtual environment activated
    ✓ Dependencies installed
    ✓ Database services started
    
    Starting server on http://localhost:8000
    
    API Documentation:
      • Swagger UI: http://localhost:8000/docs
      • ReDoc: http://localhost:8000/redoc
      • OpenAPI JSON: http://localhost:8000/openapi.json
    
    Press Ctrl+C to stop
```

### 3. `scripts/test_api.sh` (150+ lines)

Comprehensive curl examples для тестирования всех endpoints:

```bash
#!/usr/bin/env bash
# API testing script with curl

Includes:
✅ Health check endpoint
✅ Create subscription (201 Created)
✅ List subscriptions (200 OK)
✅ Get subscription (200 OK)
✅ Partial update subscription (200 OK)
✅ Pause subscription (200 OK)
✅ Resume subscription (200 OK)
✅ Delete subscription (204 No Content)
✅ Error scenarios (404, 422, 400)

Usage:
    $ chmod +x scripts/test_api.sh
    $ ./scripts/test_api.sh

Prerequisites:
    - jq (JSON query tool): brew install jq
    - curl (pre-installed on macOS/Linux)
    - Server running on http://localhost:8000
```

## Application Startup Flow

```
1. ASGI Server (uvicorn) starts
   ↓
2. FastAPI app initialized via create_app()
   ↓
3. startup event triggered
   ├─ init_db() called
   │  ├─ Create engine connection
   │  ├─ Create tables (if not exist)
   │  └─ Verify connection
   └─ Logging: "✓ Database initialized"
   ↓
4. Routes registered
   ├─ /health
   ├─ /
   ├─ /alerts/subscriptions (and sub-routes)
   └─ Exception handlers attached
   ↓
5. Server listens on 0.0.0.0:8000
   ├─ Ready for requests
   └─ Docs available at /docs
   ↓
6. On shutdown
   ├─ shutdown event triggered
   ├─ close_db() called
   │  ├─ Close all sessions
   │  └─ Cleanup connections
   └─ Logging: "✓ Resources cleaned up"
```

## Error Handling Architecture

```
HTTP Request
  ↓
FastAPI Route Handler
  ↓
[Exception Raised]
  ↓
Exception Handlers (Priority Order):
  1. PydanticValidationError     → 422 with field errors
  2. ValueError                  → 400 Bad Request
  3. Exception (catch-all)       → 500 Internal Server Error
  ↓
JSONResponse with:
  - status_code
  - message
  - errors (if applicable)
  ↓
HTTP Response sent to client
```

## Logging Configuration

```python
import logging
logger = logging.getLogger(__name__)

Levels used:
- logger.info()      - General events (startup, shutdown)
- logger.warning()   - Non-critical issues (validation errors)
- logger.error()     - Unexpected errors (exceptions)
- logger.critical()  - Fatal errors (DB init failure)

Output example:
    INFO:src.weather_alerts.api.main:Starting Weather Alerts API...
    INFO:src.weather_alerts.api.main:✓ Database initialized successfully
    WARNING:src.weather_alerts.api.main:Validation error on GET /alerts/subscriptions: 1 errors
```

## Running Locally

### Quick Start (Recommended)

```bash
# Terminal 1: Start development server
cd /path/to/itmo-practice-xopiumm
chmod +x scripts/run_dev.sh
./scripts/run_dev.sh

# Opens:
# - API: http://localhost:8000
# - Docs: http://localhost:8000/docs
# - ReDoc: http://localhost:8000/redoc
```

### Manual Start (Direct uvicorn)

```bash
# Terminal 1: Activate environment
source .venv/bin/activate

# Terminal 2: Start docker-compose services
docker-compose up

# Terminal 1: Run server
uvicorn src.weather_alerts.api.main:app --reload
```

### Direct Python (Without uvicorn)

```python
from src.weather_alerts.api.main import create_app
import uvicorn

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
    )

# Run:
# $ python -c "from src.weather_alerts.api.main import create_app; ..."
```

## Testing

### Automated Test Script

```bash
chmod +x scripts/test_api.sh
./scripts/test_api.sh
```

### Manual curl Examples

#### Health Check
```bash
curl http://localhost:8000/health
# Response: {"status": "ok"}
```

#### Create Subscription
```bash
curl -X POST http://localhost:8000/alerts/subscriptions \
  -H "Content-Type: application/json" \
  -d '{
    "location": {"id": 1},
    "conditions": [{"type": "rain_probability_above", "threshold_value": 70}],
    "delivery_channels": [{"type": "email", "destination": "user@example.com"}]
  }'
# Response: 201 Created
```

#### List Subscriptions
```bash
curl http://localhost:8000/alerts/subscriptions
# Response: 200 OK with list
```

#### Pause Subscription
```bash
curl -X POST http://localhost:8000/alerts/subscriptions/1/pause
# Response: 200 OK with paused subscription
```

### Error Testing

#### Missing Required Field
```bash
curl -X POST http://localhost:8000/alerts/subscriptions \
  -H "Content-Type: application/json" \
  -d '{"location": {"id": 1}}'
# Response: 422 Unprocessable Entity
# Body: {"status_code": 422, "message": "Invalid request data", "errors": [...]}
```

#### Invalid Subscription ID
```bash
curl http://localhost:8000/alerts/subscriptions/9999
# Response: 404 Not Found
# Body: {"status_code": 404, "message": "Subscription 9999 not found"}
```

## OpenAPI Documentation

Automatically generated and available at:
- **Swagger UI**: `/docs`
- **ReDoc**: `/redoc`
- **JSON Schema**: `/openapi.json`

Features:
✅ All endpoints documented with descriptions
✅ Request/response schemas with examples
✅ Try-it-out functionality in Swagger UI
✅ Status codes and error responses documented
✅ Path/query parameter documentation

## Production Considerations

### Database Migrations (instead of init_db)

Instead of `await init_db()` in startup, use Alembic:

```python
# Production startup (pseudo-code)
@app.on_event("startup")
async def startup_event():
    # Don't create tables, assume migrations ran
    # Just verify connection
    async with get_engine() as engine:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
```

### Logging

Enable structured JSON logging:

```python
import structlog

structlog.configure(
    processors=[
        structlog.processors.JSONRenderer()
    ]
)
```

### CORS (if needed)

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://example.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### HTTPS

Use in production:

```bash
uvicorn src.weather_alerts.api.main:app \
  --ssl-keyfile=/path/to/key.pem \
  --ssl-certfile=/path/to/cert.pem \
  --host 0.0.0.0 \
  --port 443
```

## Files Modified
- Updated: `src/weather_alerts/api/main.py` (200+ lines)
- Created: `scripts/run_dev.sh`
- Created: `scripts/test_api.sh`

## Next Steps

- **T013:** Authentication implementation (OAuth2/JWT)
- **Phase 3:** Weather evaluation service
- **Phase 4:** Delivery channels implementation
- **Phase 5:** Retry logic and monitoring

## Dependencies

Already in requirements.txt:
- **fastapi** (0.104.1)
- **uvicorn** (0.24.0+) - ASGI server
- **sqlalchemy** (2.0+)
- **pydantic** (2.5.0+)
- **asyncpg** - PostgreSQL driver

Optional for testing:
- **curl** - HTTP client
- **jq** - JSON query tool

