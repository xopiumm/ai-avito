"""Practical examples of structured logging and correlation ID usage.

This file demonstrates best practices for using structured logging throughout
the Weather Alerts application - in API handlers, services, and background tasks.

For comprehensive documentation, see:
- src/weather_alerts/config/logging.py
- src/weather_alerts/api/middleware/request_context.py
"""

# ============================================================================
# EXAMPLE 1: Using logger in FastAPI route handler
# ============================================================================

"""
from fastapi import APIRouter, Request
from src.weather_alerts.config.logging import get_logger
from src.weather_alerts.api.middleware.request_context import get_correlation_id_from_request

router = APIRouter(prefix="/alerts/subscriptions", tags=["subscriptions"])
logger = get_logger(__name__)

@router.post("/")
async def create_subscription(subscription: SubscriptionCreate, request: Request):
    '''Create a new subscription with structured logging.'''
    
    # Get correlation ID from request context (set by middleware)
    correlation_id = get_correlation_id_from_request(request)
    
    # Logger automatically includes correlation_id in all logs for this request
    logger.info(
        "Creating new subscription",
        extra={
            "user_id": request.state.user_id,
            "location": subscription.location,
            "conditions_count": len(subscription.conditions),
        }
    )
    
    try:
        # Business logic...
        result = await subscription_service.create(subscription)
        
        logger.info(
            "Subscription created successfully",
            extra={
                "subscription_id": result.id,
                "location": subscription.location,
            }
        )
        return result
        
    except ValueError as e:
        logger.warning(
            f"Invalid subscription data: {e}",
            extra={"error": str(e)}
        )
        raise
        
    except Exception as e:
        logger.exception(
            "Failed to create subscription",
            extra={"error": str(e)}
        )
        raise
"""

# ============================================================================
# EXAMPLE 2: Using logger in service layer
# ============================================================================

"""
from src.weather_alerts.config.logging import get_logger

class NotificationService:
    def __init__(self):
        self.logger = get_logger(__name__)
    
    async def send_notifications(self, subscription_id: str, event: WeatherEvent):
        '''Send notifications for triggered weather event.'''
        
        # correlation_id is automatically included from context
        self.logger.info(
            "Processing weather event",
            extra={
                "subscription_id": subscription_id,
                "event_type": event.type,
                "event_severity": event.severity,
            }
        )
        
        # Channels will be logged separately to allow easy filtering
        channels = await self.get_active_channels(subscription_id)
        for channel in channels:
            try:
                self.logger.debug(
                    f"Sending via {channel.type}",
                    extra={"channel_id": channel.id}
                )
                await self.send_to_channel(channel, event)
                
            except Exception as e:
                # Isolated failure doesn't block other channels
                self.logger.error(
                    f"Failed to send via {channel.type}",
                    extra={
                        "channel_id": channel.id,
                        "error": str(e),
                    }
                )
                continue
"""

# ============================================================================
# EXAMPLE 3: Using logger in Celery task
# ============================================================================

"""
from src.weather_alerts.config.logging import get_logger
from src.weather_alerts.workers import app
from src.weather_alerts.workers.delivery_tasks import DeliveryTaskPayload

logger = get_logger(__name__)

@app.task(
    name="send_email_notification",
    bind=True,
    queue="email"
)
def send_email_notification(self, payload_dict: dict):
    '''Send email with correlation ID from task metadata.'''
    
    payload = DeliveryTaskPayload.from_dict(payload_dict)
    
    # Set correlation ID from metadata (so all logs are correlated)
    from src.weather_alerts.config.logging import set_correlation_id
    if metadata_correlation_id := payload.metadata.get("correlation_id"):
        set_correlation_id(metadata_correlation_id)
    
    logger.info(
        "Starting email send task",
        extra={
            "task_id": self.request.id,
            "recipient": payload.recipient_id,
            "attempt": payload.attempt_number,
        }
    )
    
    try:
        result = send_email(payload.recipient_id, payload.content)
        logger.info("Email sent successfully")
        return result
        
    except Exception as e:
        logger.exception(f"Email send failed: {e}")
        raise
"""

# ============================================================================
# EXAMPLE 4: Structured logging patterns
# ============================================================================

"""
from src.weather_alerts.config.logging import get_logger, set_correlation_id, set_user_id

logger = get_logger(__name__)

# Pattern 1: Business event with metadata
logger.info(
    "Subscription enabled",
    extra={
        "subscription_id": "sub_123",
        "user_id": "user_456",
        "location": "New York",
    }
)

# Pattern 2: Error with context
try:
    weather_data = fetch_weather("Invalid Location")
except ValueError as e:
    logger.warning(
        f"Weather fetch failed: {e}",
        extra={
            "location": location,
            "provider": "openweathermap",
            "retry_count": 3,
        }
    )

# Pattern 3: Performance tracking
import time
start = time.time()
logger.info(
    "Processing batch notifications",
    extra={"batch_size": 1000}
)
# ... do work ...
duration = (time.time() - start) * 1000
logger.info(
    "Batch processing completed",
    extra={
        "batch_size": 1000,
        "duration_ms": round(duration, 2),
        "succeeded": 987,
        "failed": 13,
    }
)

# Pattern 4: Manual context setting (for special cases)
set_correlation_id("manual_task_xyz")
set_user_id("admin_user")
logger.info("Admin action performed", extra={"action": "delete_subscription"})
"""

# ============================================================================
# EXAMPLE 5: Log output formats
# ============================================================================

"""
DEVELOPMENT (Human-readable):
[10:30:45.123] INFO     src.weather_alerts.services.notification_service:
    Processing notification (corr=req_550e, user=user_1, path=/alerts/subscriptions)
    [subscription_id=sub_123, event_type=rain]

PRODUCTION (JSON):
{
    "timestamp": "2026-04-09T10:30:45.123Z",
    "level": "INFO",
    "logger": "src.weather_alerts.services.notification_service",
    "message": "Processing notification",
    "correlation_id": "req_550e8400-e29b-41d4-a716-446655440000",
    "user_id": "user_1",
    "request_path": "/alerts/subscriptions",
    "subscription_id": "sub_123",
    "event_type": "rain"
}

Log aggregation (CloudWatch, ELK, etc.):
- Filter by correlation_id: Get all logs for one request
- Filter by user_id: Audit trail for specific user
- Filter by request_path: Per-endpoint metrics
- Calculate duration: Parse timestamp and duration_ms
- Error tracking: Filter by level=ERROR and group by logger
"""

# ============================================================================
# EXAMPLE 6: Correlation ID flow through a complete request
# ============================================================================

"""
1. Client sends request with optional X-Correlation-ID header:
   POST /alerts/subscriptions
   X-Correlation-ID: client_123

2. RequestContextMiddleware receives request:
   - Extracts or generates correlation_id
   - Sets in async context (all logs will include it)
   - Adds to request.state
   - Returns correlation_id in X-Correlation-ID response header

3. Route handler processes request:
   - All logger.info() calls auto-include correlation_id
   - Can access from request.state.correlation_id if needed

4. Route handler submits background task:
   - Passes correlation_id in task metadata
   
5. Celery worker receives task:
   - CeleryTaskContextMiddleware sets correlation_id
   - All worker logs include same correlation_id as original request
   - End-to-end tracing: one correlation_id spans request → worker → delivery

6. Client receives response:
   X-Correlation-ID: client_123
   (Same ID allows client to correlate their logs with server logs)

RESULT:
- All logs for this flow have correlation_id = "client_123"
- Aggregate command: grep "correlation_id: client_123" /var/log/weather_alerts.log
- See: request handler → service → worker → delivery → final status
"""

# ============================================================================
# EXAMPLE 7: Setting up logging in main.py (already done)
# ============================================================================

"""
from src.weather_alerts.config.logging import configure_logging, get_logger
from src.weather_alerts.api.middleware.request_context import RequestContextMiddleware

def create_app():
    # Configure logging from settings (before creating app)
    configure_logging()
    
    app = FastAPI(...)
    
    # Add request context middleware (manages correlation ID)
    app.add_middleware(RequestContextMiddleware)
    
    return app

# In workers/celery_app.py:
from src.weather_alerts.config.logging import get_logger
logger = get_logger(__name__)
"""

# ============================================================================
# LOG FILTERING & QUERYING EXAMPLES
# ============================================================================

"""
CLI Examples (with jq on Linux/Mac):

# Get all logs for a specific request
grep "correlation_id: req_550e" /var/log/weather_alerts.log

# Parse JSON and filter by correlation_id
cat /var/log/weather_alerts.log | jq 'select(.correlation_id == "req_550e...'

# Find all errors in last hour
cat /var/log/weather_alerts.log | jq 'select(.level == "ERROR") | .timestamp'

# Count errors per logger
cat /var/log/weather_alerts.log | jq '.logger' | sort | uniq -c

# Find slow requests (duration > 5 seconds)
cat /var/log/weather_alerts.log | jq 'select(.duration_ms > 5000)'

# Get all logs from specific user
cat /var/log/weather_alerts.log | jq 'select(.user_id == "user_123")'

Log aggregation system commands (e.g., CloudWatch):

# All errors
logs | filter level = "ERROR" | stats count()

# P99 duration for POST /subscriptions
logs | filter request_path = "/subscriptions" and method = "POST" 
     | stats pct(duration_ms, 99)

# Delivery failures by channel
logs | filter logger = "delivery_tasks" and level = "ERROR" 
     | stats count() by channel
"""
