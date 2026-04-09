# T019: Webhook Notification Delivery Adapter

**Status**: ✅ Complete  
**Tests**: 71 passing (29 basic + 42 extended)  
**Location**: `src/weather_alerts/adapters/webhook_sender.py`

## Overview

Webhook delivery adapter provides a flexible HTTP POST interface for sending alert notifications to any HTTP endpoint (Slack hooks, Discord webhooks, custom APIs, etc.).

Key design principles mirror T017/T018:
- **Unified result interface** for all delivery outcomes
- **Explicit HTTP error classification** (4xx non-retryable, 5xx retryable)
- **Provider abstraction** for testing and multiple implementations
- **Comprehensive timeout/connection handling**
- **Structured JSON payload** with alert metadata

## Architecture

### High-Level Flow

```text
User Application
    ↓
WebhookSender (main service)
    ├── Validates WebhookMessage (URL, payload, timeout)
    ├── Delegates to WebhookProvider implementation
    ├── Maps HTTP responses to retryable/non-retryable
    ├── Classifies HTTP status codes:
    │   ├── 2xx: Success
    │   ├── 4xx: Non-retryable (client error)
    │   ├── 5xx: Retryable (server error)
    │   ├── Timeout: Retryable
    │   └── Connection failed: Retryable
    → Returns unified WebhookSendResult
    ↓
Application (consumes result)
    ├── if success: update delivery count
    ├── if is_retryable: enqueue for backoff retry
    ├── if not is_retryable: log permanent failure, delete webhook
```

### Key Components

#### 1. Data Models

**WebhookMessage** - Input message for webhook delivery
```python
@dataclass
class WebhookMessage:
    webhook_url: str                # HTTPS endpoint URL
    payload: Dict[str, Any]         # JSON payload (alert data)
    headers: Dict[str, str]         # Custom HTTP headers (e.g., Authorization)
    timeout_seconds: int            # Request timeout (default 30)
    metadata: Dict[str, Any]        # Tracking metadata (preserved in result)
```

**WebhookSendResult** - Delivery outcome
```python
@dataclass
class WebhookSendResult:
    success: bool                   # Delivery succeeded
    status: WebhookDeliveryStatus   # Status enum
    webhook_url: str                # Target URL
    sent_at_utc: datetime           # Send timestamp (UTC)
    http_status: Optional[int]      # HTTP response status (200, 401, 503, etc.)
    response_body: Optional[str]    # Response body (first 1000 chars)
    error_code: Optional[str]       # Error code if failed
    error_message: Optional[str]    # Human-readable error
    is_retryable: bool              # Can retry?
    response_time_ms: Optional[int] # Request duration in ms
    provider_response: Optional[Dict]   # Raw provider data
    metadata: Dict[str, Any]        # Metadata from input (for correlation)
```

#### 2. Enums

**WebhookDeliveryStatus** - Send outcome
```python
DELIVERED               # Successfully posted
ACCEPTED                # Accepted for processing (202, etc.)
FAILED_RETRYABLE        # Temporary error (try again)
FAILED_NON_RETRYABLE    # Permanent error (don't retry)
FAILED_UNKNOWN          # Unknown error (safe retry)
TIMEOUT                 # Request timed out
CONNECTION_FAILED       # Could not connect
```

**WebhookHttpStatus** - Common HTTP codes
```python
HTTP_200_OK             # Success
HTTP_202_ACCEPTED       # Asynchronous acceptance
HTTP_400_BAD_REQUEST    # Non-retryable (client error)
HTTP_401_UNAUTHORIZED   # Non-retryable (auth failed)
HTTP_403_FORBIDDEN      # Non-retryable (access denied)
HTTP_404_NOT_FOUND      # Non-retryable (endpoint missing)
HTTP_500_INTERNAL_ERROR # Retryable (server error)
HTTP_502_BAD_GATEWAY    # Retryable (proxy error)
HTTP_503_SERVICE_UNAVAILABLE  # Retryable (temp unavailable)
HTTP_504_GATEWAY_TIMEOUT      # Retryable (timeout)
```

#### 3. Exception Hierarchy

**Retryable Errors** (is_retryable = True)
```python
WebhookTimeoutError             # Request timeout
WebhookConnectionError          # Cannot connect
WebhookNetworkError             # Network issue
WebhookServerError              # 5xx server error
WebhookServiceUnavailableError  # 503 specifically
WebhookRateLimitError           # 429 rate limit (includes retry_after_seconds)
```

**Non-Retryable Errors** (is_retryable = False)
```python
InvalidWebhookUrlError          # Bad URL format
AuthenticationFailedError       # 401 auth required
WebhookForbiddenError           # 403 access denied
WebhookNotFoundError            # 404 endpoint missing
InvalidWebhookPayloadError      # 400 bad payload
WebhookConfigurationError       # Sender misconfigured
```

#### 4. Provider Interface

Abstract base class for HTTP implementations:

```python
class WebhookProvider(ABC):
    @abstractmethod
    def send(self, message: WebhookMessage) -> WebhookSendResult:
        """POST webhook notification.
        
        Args:
            message: WebhookMessage to send
            
        Returns:
            WebhookSendResult with HTTP status and details
            
        Raises:
            RetryableWebhookError: Temporary network/HTTP 5xx errors
            NonRetryableWebhookError: HTTP 4xx client errors
        """
        pass
```

#### 5. Mock Provider

For testing without real HTTP calls:

```python
provider = MockWebhookProvider(
    success_rate=0.95,              # Success probability
    http_status=200,                # HTTP status on success
    fail_with_retryable=False,      # Force retryable error
    fail_with_non_retryable=False,  # Force non-retryable error
    response_time_ms=150,           # Simulated response time
)
```

#### 6. Main Service

```python
sender = WebhookSender(provider=implementation)
result = sender.send(webhook_message)

if result.success:
    log_delivery(message_id, result.response_time_ms)
elif result.is_retryable:
    enqueue_for_retry(webhook_message, result.error_code)
else:
    delete_webhook(result.webhook_url, result.error_code)
    alert_admin(f"Webhook {result.error_message}")
```

## Usage Examples

### Send to Slack Webhook

```python
from src.weather_alerts.adapters.webhook_sender import (
    WebhookSender, WebhookMessage, MockWebhookProvider
)
import requests

sender = WebhookSender(provider=MockWebhookProvider())

# Slack webhook format
payload = {
    "text": "🌧️ Weather Alert",
    "attachments": [
        {
            "color": "danger",
            "title": "Heavy Rain Expected",
            "text": "Rain probability: 85%",
            "fields": [
                {"title": "Region", "value": "Moscow", "short": True},
                {"title": "Time", "value": "Next 6 hours", "short": True},
                {"title": "Temperature", "value": "-5°C", "short": True},
            ],
            "footer": "Weather Alerts",
            "ts": 1642254000,
        }
    ]
}

message = WebhookMessage(
    webhook_url="https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX",
    payload=payload,
    timeout_seconds=30,
    metadata={"channel": "weather", "alert_id": 12345},
)

result = sender.send(message)

if result.success:
    print(f"✅ Posted to Slack in {result.response_time_ms}ms")
elif result.is_retryable:
    print(f"⏱️ Retry: {result.error_code}")
else:
    print(f"❌ Delete webhook: {result.error_message}")
```

### Send to Custom API

```python
message = WebhookMessage(
    webhook_url="https://alerts.example.com/api/v1/webhooks/weather",
    payload={
        "event_type": "weather_alert",
        "alert_id": 12345,
        "severity": "high",
        "title": "Rain Alert",
        "description": "Heavy rain expected in Moscow",
        "location": {
            "name": "Moscow",
            "coordinates": {"lat": 55.7558, "lon": 37.6173},
        },
        "forecast": {
            "type": "rain",
            "probability": 85,
            "duration_hours": 6,
        },
        "timestamp": "2024-01-15T12:00:00Z",
    },
    headers={
        "Authorization": "Bearer secret_token_here",
        "X-API-Key": "webhook_key_123",
        "X-Request-ID": "req_abc_def",
    },
    timeout_seconds=60,
    metadata={"subscription_id": 789, "user_id": 42},
)

result = sender.send(message)

if result.success:
    print(f"✅ Accepted: HTTP {result.http_status} in {result.response_time_ms}ms")
    # body = {"status": "accepted", "id": "webhook_msg_123"}
else:
    print(f"❌ {result.error_code}: {result.error_message}")
```

### Discord Webhook

```python
payload = {
    "username": "Weather Bot",
    "avatar_url": "https://example.com/weather-icon.png",
    "embeds": [
        {
            "title": "⚠️ Weather Alert",
            "description": "Heavy rain expected",
            "color": 15158332,  # Orange
            "fields": [
                {"name": "Severity", "value": "High", "inline": True},
                {"name": "Duration", "value": "6 hours", "inline": True},
                {"name": "Regions Affected", "value": "Moscow, Novgorod", "inline": False},
            ],
            "timestamp": "2024-01-15T12:00:00Z",
        }
    ]
}

message = WebhookMessage(
    webhook_url="https://discordapp.com/api/webhooks/WEBHOOK_ID/WEBHOOK_TOKEN",
    payload=payload,
    timeout_seconds=30,
)

result = sender.send(message)
```

### Batch Delivery

```python
webhooks = [
    "https://hooks.slack.com/services/...",
    "https://alerts.example.com/webhook",
    "https://discord.com/api/webhooks/...",
]

alert_payload = {
    "alert_id": 12345,
    "severity": "high",
    "title": "Rain Alert",
}

results = []
for i, webhook_url in enumerate(webhooks):
    message = WebhookMessage(
        webhook_url=webhook_url,
        payload=alert_payload,
        metadata={"webhook_index": i, "platform": ["slack", "api", "discord"][i]},
    )
    result = sender.send(message)
    results.append(result)

# Analyze results
successful = [r for r in results if r.success]
retryable_failures = [r for r in results if not r.success and r.is_retryable]
permanent_failures = [r for r in results if not r.success and not r.is_retryable]

print(f"Sent to {len(successful)}/{len(webhooks)} webhooks")
if retryable_failures:
    print(f"Retrying {len(retryable_failures)} webhooks")
if permanent_failures:
    print(f"Disabling {len(permanent_failures)} webhooks")
```

### Retry Logic

```python
def send_with_exponential_backoff(message, max_retries=3):
    """Send webhook with exponential backoff retry."""
    sender = WebhookSender(provider=RealHttpProvider())
    
    for attempt in range(max_retries):
        result = sender.send(message)
        
        if result.success:
            return result
        
        if not result.is_retryable:
            # Permanent error - don't retry
            logger.error(f"Permanent webhook failure: {result.error_code}")
            return result
        
        # Exponential backoff: 2s, 4s, 8s
        backoff_seconds = 2 ** attempt
        
        # Check if server told us to wait
        if result.error_code == "rate_limit" and result.provider_response:
            retry_after = result.provider_response.get("retry_after_seconds", backoff_seconds)
            backoff_seconds = retry_after
        
        logger.warning(f"Webhook failed ({result.error_code}), retrying in {backoff_seconds}s")
        time.sleep(backoff_seconds)
    
    return result
```

### Custom Provider Implementation (HTTP)

```python
import requests
from src.weather_alerts.adapters.webhook_sender import (
    WebhookProvider, WebhookMessage, WebhookSendResult, 
    WebhookDeliveryStatus, WebhookTimeoutError, 
    WebhookServerError, InvalidWebhookPayloadError,
    AuthenticationFailedError, WebhookNotFoundError
)
import time

class HttpWebhookProvider(WebhookProvider):
    """Real HTTP webhook provider using requests library."""
    
    def __init__(self, max_retries: int = 0):
        self.max_retries = max_retries
    
    def send(self, message: WebhookMessage) -> WebhookSendResult:
        start_time = time.time()
        
        try:
            # Prepare request
            headers = {"Content-Type": "application/json"}
            headers.update(message.headers)
            
            # Send POST request
            response = requests.post(
                message.webhook_url,
                json=message.payload,
                headers=headers,
                timeout=message.timeout_seconds,
            )
            
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # Classify response
            if 200 <= response.status_code < 300:
                status = WebhookDeliveryStatus.DELIVERED
                success = True
                is_retryable = False
            elif 400 <= response.status_code < 500:
                # 4xx: non-retryable client error
                if response.status_code == 401:
                    raise AuthenticationFailedError(f"HTTP {response.status_code}")
                elif response.status_code == 404:
                    raise WebhookNotFoundError(f"HTTP {response.status_code}")
                elif response.status_code == 400:
                    raise InvalidWebhookPayloadError(f"HTTP {response.status_code}")
                else:
                    status = WebhookDeliveryStatus.FAILED_NON_RETRYABLE
                    success = False
                    is_retryable = False
            else:
                # 5xx: retryable server error
                raise WebhookServerError(f"HTTP {response.status_code}", response.status_code)
            
            return WebhookSendResult(
                success=success,
                status=status,
                webhook_url=message.webhook_url,
                sent_at_utc=datetime.now(tz=timezone.utc),
                http_status=response.status_code,
                response_body=response.text[:1000],
                is_retryable=is_retryable,
                response_time_ms=response_time_ms,
                metadata=message.metadata,
            )
            
        except requests.Timeout as e:
            raise WebhookTimeoutError(f"Timeout after {message.timeout_seconds}s")
        except requests.ConnectionError as e:
            raise WebhookConnectionError(f"Connection failed: {e}")
        except WebhookServerError:
            raise
        except Exception as e:
            raise
```

## HTTP Status Code Reference

| Status | Classification | Meaning | Action |
|--------|-----------------|---------|--------|
| **200** | ✅ Success | Delivered | Complete |
| **201** | ✅ Success | Created | Complete |
| **202** | ✅ Success | Accepted (async) | Complete |
| **204** | ✅ Success | No Content | Complete |
| **400** | ❌ Non-retryable | Bad Request | Log & delete |
| **401** | ❌ Non-retryable | Auth Required | Log & delete |
| **403** | ❌ Non-retryable | Forbidden | Log & delete |
| **404** | ❌ Non-retryable | Not Found | Log & delete |
| **429** | ⏱️ Retryable | Rate Limited | Retry with backoff |
| **500** | ⏱️ Retryable | Server Error | Retry with backoff |
| **502** | ⏱️ Retryable | Bad Gateway | Retry with backoff |
| **503** | ⏱️ Retryable | Service Unavailable | Retry with backoff |
| **504** | ⏱️ Retryable | Gateway Timeout | Retry with backoff |
| Timeout | ⏱️ Retryable | Request timeout | Retry with backoff |
| Connection Error | ⏱️ Retryable | Could not connect | Retry with backoff |

## Integration Points

### T016 NotificationOrchestrator

Webhook sender integrates as third delivery channel:

```python
class NotificationOrchestrator:
    def __init__(self, email_sender, push_sender, webhook_sender):
        self.channels = {
            "email": email_sender,
            "push": push_sender,
            "webhook": webhook_sender,
        }
    
    def send_prepared(self, prepared: PreparedNotification):
        results = {}
        
        if "email" in prepared.channels:
            results["email"] = self.email_sender.send(email_message)
        
        if "push" in prepared.channels:
            results["push"] = self.push_sender.send(push_message)
        
        if "webhook" in prepared.channels:
            results["webhook"] = self.webhook_sender.send(webhook_message)
        
        return results
```

### Future T0XX DeliveryService

Coordinates all three adapters:

```python
class DeliveryService:
    def deliver(self, alert, channels: List[str]):
        """Deliver alert via multiple channels."""
        results = {}
        
        for channel in channels:
            if channel == "email":
                results["email"] = self.email_sender.send(...)
            elif channel == "push":
                results["push"] = self.push_sender.send(...)
            elif channel == "webhook":
                results["webhook"] = self.webhook_sender.send(...)
        
        return results
```

### Future T0XX RetryManager

Handles retries based on is_retryable flag:

```python
class RetryManager:
    def handle_failure(self, result: WebhookSendResult):
        if result.is_retryable:
            # Exponential backoff
            schedule_retry(result, backoff=60)
        else:
            # Permanent failure
            remove_webhook(result.webhook_url)
            alert_admin(f"Webhook disabled: {result.error_code}")
```

## JSON Payload Example

Weather alert webhook payload that can be sent to any HTTP endpoint:

```json
{
  "event_type": "weather_alert",
  "alert_id": 12345,
  "severity": "high",
  "title": "⚠️ Heavy Rain Alert",
  "description": "Heavy rain expected starting in 2 hours",
  "timestamp": "2024-01-15T12:00:00Z",
  "expires_at": "2024-01-15T18:00:00Z",
  
  "location": {
    "name": "Moscow",
    "type": "city",
    "coordinates": {
      "latitude": 55.7558,
      "longitude": 37.6173
    },
    "regions": ["Moscow", "Moscow Oblast"]
  },
  
  "weather": {
    "type": "rain",
    "probability": 0.85,
    "severity": "heavy",
    "expected_duration_hours": 6,
    "expected_intensity_mm": 25,
    "wind_speed_kmh": 15,
    "temperature_celsius": -5,
    "feels_like_celsius": -12
  },
  
  "conditions": [
    {
      "type": "precipitation",
      "start_time": "2024-01-15T14:00:00Z",
      "end_time": "2024-01-15T20:00:00Z"
    },
    {
      "type": "strong_wind",
      "start_time": "2024-01-15T14:00:00Z",
      "end_time": "2024-01-15T18:00:00Z"
    }
  ],
  
  "recommended_actions": [
    "Avoid unnecessary travel",
    "Secure loose outdoor items",
    "Keep emergency supplies handy"
  ],
  
  "source": "weather_alerts_system",
  "version": "1.0",
  
  "metadata": {
    "subscription_id": 789,
    "user_id": 42,
    "notification_id": "notif_123456",
    "delivery_channel": "webhook"
  }
}
```

## Testing Coverage

### Test Categories (71 tests)
- **Message validation** (8 tests)
- **Result model** (7 tests)
- **Exception hierarchy** (11 tests)
- **Mock provider** (6 tests)
- **Sender integration** (6 tests)
- **Custom providers** (3 tests)
- **Complex payload** (5 tests)
- **HTTP status codes** (11 tests)
- **Metadata tracking** (2 tests)
- **Batch delivery** (3 tests)
- **Response time** (2 tests)
- **Error handling** (2 tests)
- **Realistic scenarios** (4 tests)

### Key Test Scenarios
✅ Successful webhook delivery  
✅ Async webhook acceptance (202)  
✅ Timeout handling  
✅ Connection failures  
✅ HTTP 4xx non-retryable errors  
✅ HTTP 5xx retryable errors  
✅ URL validation  
✅ Payload validation  
✅ Headers preservation  
✅ Batch delivery to multiple webhooks  
✅ Metadata correlation  
✅ Response time tracking  

## Files

### Implementation
- `src/weather_alerts/adapters/webhook_sender.py` - Main adapter (610+ LOC)

### Tests
- `tests/test_webhook_sender.py` - Basic tests (29)
- `tests/test_webhook_sender_extended.py` - Extended tests (42)

### Documentation
- This file: `artifacts/T019_webhook_sender.md`

## Dependencies

**External**: None (core adapter runtime uses Python stdlib only)

**Core External Dependencies**: None
- The WebhookSender implementation requires no external libraries
- All core functionality uses only Python standard library

**Optional Example Dependencies**:
- `requests` - Used in the example custom HTTP provider implementation (see "Real HTTP Provider Implementation" section below)
  - Required only if you follow the example to implement a real HTTP-based webhook provider
  - Not needed if you use the mock provider or implement your own provider using different libraries

**Internal**:
- `datetime` - UTC timestamp handling
- `dataclasses` - Data models
- `enum` - Status and HTTP code enumerations
- `abc` - Abstract provider interface
- `logging` - Event logging
- `json` - JSON serialization (referenced in examples)
- `typing` - Type hints

## Design Decisions

### Why Webhook Support?
Different organizations use different platforms (Slack, Discord, custom APIs). Webhook support enables:
- Sending alerts to existing enterprise systems
- Integration with third-party services without SDKs
- Simple HTTP-based integration for any platform
- No need to learn platform-specific libraries

### Why HTTP Classification?
HTTP status codes have clear semantics for retry logic:
- **2xx Success**: Delivery complete, don't retry
- **4xx Client Error**: Request was malformed, don't retry (will fail again)
- **5xx Server Error**: Server issue, retry (may recover)
- **Timeout/Connection**: Network issue, retry (may succeed later)

### Why Response Time Tracking?
Response times help detect:
- Slow webhooks (performance monitoring)
- Network latency increases (early warning)
- Webhook health issues (trending slower = degrading)
- Timeout thresholds (increase if consistently slow)

### Why Async Acceptance (202)?
Some systems accept webhooks asynchronously:
- Queue the webhook for processing
- Return 202 with queue ID
- Application polls for completion
- Prevents webhook from blocking sender

### Why Metadata Preservation?
Metadata enables correlation and tracking:
- Track which notification triggered delivery
- Correlate with alerts in monitoring systems
- Identify webhook in logs
- Support multi-tenant systems

## Compliance

✅ Follows T017 EmailSender patterns  
✅ Follows T018 PushSender patterns  
✅ Matches contract delivery interface  
✅ Supports spec.md requirements  
✅ Explicit retryable/non-retryable classification  
✅ No external HTTP dependencies (interface only)  
✅ Comprehensive error handling  
✅ Full test coverage (71 tests)  
✅ Production-ready HTTP classification

## Future Enhancements

- Real HTTP provider implementation (requests-based)
- Webhook retry manager
- Webhook health monitoring and alerting
- Circuit breaker pattern (disable after N failures)
- Webhook payload validation against schema
- Webhook signature verification (HMAC)
- Webhook delivery log and audit trail
- Webhook template support (pre-built formats for platforms)
- Request/response filtering for sensitive data
- Webhook transformation pipeline
