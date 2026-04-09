"""Webhook delivery adapter for alerts.

This module provides a flexible webhook notification interface that:
- Sends HTTP POST requests to configured webhook URLs
- Distinguishes retryable from non-retryable HTTP errors
- Handles timeouts, connection errors, 4xx/5xx responses
- Enables any HTTP endpoint integration (Slack, Discord, custom CMS, etc.)
- Supports JSON payload with alert metadata
- Implements provider-agnostic interface for testing and switching

HTTP Error Classification:
- 4xx (400, 404, 401, etc.): Non-retryable (client error)
- 5xx (500, 502, 503, etc.): Retryable (server error)
- Timeout/Connection: Retryable (temporary network issue)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Dict, Any, Optional, List
import logging
import json

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS
# ============================================================================


class WebhookDeliveryStatus(str, PyEnum):
    """Webhook delivery outcome status."""
    
    DELIVERED = "delivered"                    # Successfully posted to webhook
    ACCEPTED = "accepted"                      # Webhook accepted (202 or similar)
    FAILED_RETRYABLE = "failed_retryable"      # Temporary error, should retry
    FAILED_NON_RETRYABLE = "failed_non_retryable"  # Permanent error, don't retry
    FAILED_UNKNOWN = "failed_unknown"          # Unknown error, safe retry allowed
    TIMEOUT = "timeout"                        # Request timed out
    CONNECTION_FAILED = "connection_failed"    # Could not connect to webhook


class WebhookHttpStatus(int, PyEnum):
    """Common HTTP status codes for webhooks."""
    
    # Success
    HTTP_200_OK = 200
    HTTP_201_CREATED = 201
    HTTP_202_ACCEPTED = 202
    HTTP_204_NO_CONTENT = 204
    
    # Client errors (non-retryable)
    HTTP_400_BAD_REQUEST = 400
    HTTP_401_UNAUTHORIZED = 401
    HTTP_403_FORBIDDEN = 403
    HTTP_404_NOT_FOUND = 404
    HTTP_422_UNPROCESSABLE = 422
    
    # Server errors (retryable)
    HTTP_500_INTERNAL_ERROR = 500
    HTTP_502_BAD_GATEWAY = 502
    HTTP_503_SERVICE_UNAVAILABLE = 503
    HTTP_504_GATEWAY_TIMEOUT = 504


# ============================================================================
# EXCEPTIONS: Retryable
# ============================================================================


class WebhookSenderException(Exception):
    """Base exception for webhook sending."""
    pass


class RetryableWebhookError(WebhookSenderException):
    """Temporary error that can be retried."""
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        http_status: Optional[int] = None,
        retry_after_seconds: Optional[int] = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.http_status = http_status
        self.retry_after_seconds = retry_after_seconds
        self.is_retryable = True


class WebhookTimeoutError(RetryableWebhookError):
    """Webhook request timed out."""
    
    def __init__(self, message: str = "Webhook request timed out", timeout_seconds: Optional[int] = None):
        super().__init__(message, error_code="timeout")
        self.timeout_seconds = timeout_seconds


class WebhookConnectionError(RetryableWebhookError):
    """Failed to connect to webhook endpoint."""
    
    def __init__(self, message: str = "Failed to connect to webhook"):
        super().__init__(message, error_code="connection_failed")


class WebhookNetworkError(RetryableWebhookError):
    """Network error contacting webhook."""
    
    def __init__(self, message: str = "Network error contacting webhook"):
        super().__init__(message, error_code="network_error")


class WebhookServerError(RetryableWebhookError):
    """Webhook server returned 5xx error."""
    
    def __init__(self, message: str = "Webhook server error", http_status: int = 500):
        super().__init__(
            message,
            error_code=f"server_error_{http_status}",
            http_status=http_status,
        )


class WebhookServiceUnavailableError(RetryableWebhookError):
    """Webhook service temporarily unavailable (503)."""
    
    def __init__(self, message: str = "Webhook service unavailable", retry_after_seconds: int = 60):
        super().__init__(
            message,
            error_code="service_unavailable",
            http_status=503,
            retry_after_seconds=retry_after_seconds,
        )


class WebhookRateLimitError(RetryableWebhookError):
    """Webhook rate limit exceeded (429)."""
    
    def __init__(self, message: str = "Webhook rate limit exceeded", retry_after_seconds: int = 60):
        super().__init__(
            message,
            error_code="rate_limit",
            http_status=429,
            retry_after_seconds=retry_after_seconds,
        )


# ============================================================================
# EXCEPTIONS: Non-Retryable
# ============================================================================


class NonRetryableWebhookError(WebhookSenderException):
    """Permanent error that should NOT be retried."""
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        http_status: Optional[int] = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.http_status = http_status
        self.is_retryable = False


class InvalidWebhookUrlError(NonRetryableWebhookError):
    """Webhook URL is invalid."""
    
    def __init__(self, message: str = "Invalid webhook URL"):
        super().__init__(message, error_code="invalid_url")


class AuthenticationFailedError(NonRetryableWebhookError):
    """Webhook authentication failed (401)."""
    
    def __init__(self, message: str = "Webhook authentication failed"):
        super().__init__(message, error_code="auth_failed", http_status=401)


class WebhookForbiddenError(NonRetryableWebhookError):
    """Access to webhook forbidden (403)."""
    
    def __init__(self, message: str = "Webhook access forbidden"):
        super().__init__(message, error_code="forbidden", http_status=403)


class WebhookNotFoundError(NonRetryableWebhookError):
    """Webhook endpoint not found (404)."""
    
    def __init__(self, message: str = "Webhook endpoint not found"):
        super().__init__(message, error_code="not_found", http_status=404)


class InvalidWebhookPayloadError(NonRetryableWebhookError):
    """Webhook payload is invalid (400)."""
    
    def __init__(self, message: str = "Invalid webhook payload"):
        super().__init__(message, error_code="invalid_payload", http_status=400)


class WebhookConfigurationError(NonRetryableWebhookError):
    """Webhook sender misconfigured."""
    
    def __init__(self, message: str = "Webhook sender configuration error"):
        super().__init__(message, error_code="config_error")


# ============================================================================
# DATA MODELS
# ============================================================================


@dataclass
class WebhookMessage:
    """Input message for webhook delivery.
    
    Represents an alert notification to be posted to a webhook endpoint.
    
    Attributes:
        webhook_url: HTTP endpoint URL (https://.../webhook)
        payload: Dictionary with alert data to POST as JSON
        headers: Custom HTTP headers (optional)
        timeout_seconds: Request timeout in seconds
        metadata: Custom metadata for tracking/debugging
    """
    
    webhook_url: str
    payload: Dict[str, Any]
    headers: Dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 30
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate message structure."""
        if not self.webhook_url or not isinstance(self.webhook_url, str):
            raise InvalidWebhookUrlError("'webhook_url' must be a non-empty string")
        
        if not self.webhook_url.startswith(("http://", "https://")):
            raise InvalidWebhookUrlError("'webhook_url' must start with http:// or https://")
        
        if not isinstance(self.payload, dict):
            raise InvalidWebhookPayloadError("'payload' must be a dictionary")
        
        if self.timeout_seconds <= 0:
            raise WebhookConfigurationError("'timeout_seconds' must be positive")
    
    def __repr__(self) -> str:
        return (
            f"<WebhookMessage url='{self.webhook_url[:50]}...' "
            f"payload_keys={list(self.payload.keys())[:3]} timeout={self.timeout_seconds}s>"
        )


@dataclass
class WebhookSendResult:
    """Result of webhook delivery.
    
    Attributes:
        success: Whether webhook was successfully posted
        status: WebhookDeliveryStatus enum value
        webhook_url: Target webhook URL
        sent_at_utc: Timestamp when delivery was attempted
        http_status: HTTP response status code
        response_body: Response body from webhook (first 1000 chars)
        error_code: Error code if failed
        error_message: Human-readable error description
        is_retryable: Whether this error can be retried
        response_time_ms: Time taken for request in milliseconds
        provider_response: Raw response details for debugging
        metadata: Metadata passed from input message
    """
    
    success: bool
    status: WebhookDeliveryStatus
    webhook_url: str
    sent_at_utc: datetime
    http_status: Optional[int] = None
    response_body: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    is_retryable: bool = False
    response_time_ms: Optional[int] = None
    provider_response: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __repr__(self) -> str:
        status_emoji = "✅" if self.success else "❌"
        status_text = f"HTTP {self.http_status}" if self.http_status else self.status
        return (
            f"{status_emoji} <WebhookSendResult url='{self.webhook_url[:40]}...' "
            f"status={status_text} time={self.response_time_ms}ms>"
        )


# ============================================================================
# PROVIDER INTERFACE
# ============================================================================


class WebhookProvider(ABC):
    """Abstract interface for webhook providers.
    
    Implementations must handle:
    - HTTP POST requests to configured URLs
    - Response status code handling and error classification
    - Timeout and connection error management
    - Response parsing and validation
    """
    
    @abstractmethod
    def send(self, message: WebhookMessage) -> WebhookSendResult:
        """Send webhook notification.
        
        Args:
            message: WebhookMessage to send
            
        Returns:
            WebhookSendResult with status and details
            
        Raises:
            RetryableWebhookError: For temporary errors
            NonRetryableWebhookError: For permanent errors
        """
        pass


# ============================================================================
# MOCK PROVIDER (for testing)
# ============================================================================


class MockWebhookProvider(WebhookProvider):
    """Mock provider for testing webhook notifications.
    
    Simulates webhook delivery without actual HTTP calls.
    Supports scenarios like:
    - Successful deliveries (200/202)
    - Server errors (5xx) - retryable
    - Client errors (4xx) - non-retryable
    - Timeouts
    - Connection failures
    """
    
    def __init__(
        self,
        success_rate: float = 1.0,             # 0.0-1.0 probability of success
        http_status: int = 200,                # HTTP status to return
        fail_with_retryable: bool = False,     # Force retryable error
        fail_with_non_retryable: bool = False, # Force non-retryable error
        response_time_ms: int = 100,           # Simulated response time
    ):
        """Initialize mock provider.
        
        Args:
            success_rate: Fraction of requests that succeed
            http_status: HTTP status code to return on success
            fail_with_retryable: Always fail with retryable error
            fail_with_non_retryable: Always fail with non-retryable error
            response_time_ms: Simulated response time in milliseconds
        """
        self.success_rate = success_rate
        self.http_status = http_status
        self.fail_with_retryable = fail_with_retryable
        self.fail_with_non_retryable = fail_with_non_retryable
        self.response_time_ms = response_time_ms
        self.sent_messages: List[WebhookMessage] = []
    
    def send(self, message: WebhookMessage) -> WebhookSendResult:
        """Mock send implementation."""
        import random
        
        sent_at = datetime.now(tz=timezone.utc)
        self.sent_messages.append(message)
        
        # Simulate configured failures
        if self.fail_with_non_retryable:
            return WebhookSendResult(
                success=False,
                status=WebhookDeliveryStatus.FAILED_NON_RETRYABLE,
                webhook_url=message.webhook_url,
                sent_at_utc=sent_at,
                http_status=400,
                error_code="invalid_payload",
                error_message="Webhook rejected payload (mock)",
                is_retryable=False,
                response_time_ms=self.response_time_ms,
                metadata=message.metadata,
            )
        
        if self.fail_with_retryable:
            return WebhookSendResult(
                success=False,
                status=WebhookDeliveryStatus.FAILED_RETRYABLE,
                webhook_url=message.webhook_url,
                sent_at_utc=sent_at,
                http_status=503,
                error_code="service_unavailable",
                error_message="Webhook service unavailable (mock)",
                is_retryable=True,
                response_time_ms=self.response_time_ms,
                metadata=message.metadata,
            )
        
        # Simulate success based on rate
        if random.random() < self.success_rate:
            return WebhookSendResult(
                success=True,
                status=WebhookDeliveryStatus.DELIVERED,
                webhook_url=message.webhook_url,
                sent_at_utc=sent_at,
                http_status=self.http_status,
                response_body='{"status":"acknowledged"}',
                is_retryable=False,
                response_time_ms=self.response_time_ms,
                metadata=message.metadata,
            )
        else:
            # Simulate random retryable error
            return WebhookSendResult(
                success=False,
                status=WebhookDeliveryStatus.TIMEOUT,
                webhook_url=message.webhook_url,
                sent_at_utc=sent_at,
                error_code="timeout",
                error_message="Webhook request timed out (mock)",
                is_retryable=True,
                response_time_ms=self.response_time_ms,
                metadata=message.metadata,
            )


# ============================================================================
# MAIN WEBHOOK SENDER SERVICE
# ============================================================================


class WebhookSender:
    """Main webhook notification sending service.
    
    Coordinates message validation, provider invocation, and error handling.
    Works with any WebhookProvider implementation.
    
    Features:
    - HTTP POST to any webhook endpoint
    - Intelligent HTTP status code classification:
      * 2xx: Success
      * 4xx: Non-retryable (client error)
      * 5xx: Retryable (server error)
    - Timeout and connection error handling
    - Provider abstraction for testing and provider switching
    - Comprehensive logging
    
    Usage:
        sender = WebhookSender(provider=MockWebhookProvider())
        
        message = WebhookMessage(
            webhook_url="https://hooks.example.com/alerts",
            payload={
                "alert_id": 123,
                "severity": "high",
                "title": "Rain Alert",
                "description": "Heavy rain expected",
                "timestamp": "2024-01-15T12:00:00Z",
            },
            timeout_seconds=30,
            metadata={"subscription_id": 789},
        )
        
        result = sender.send(message)
        
        if result.success:
            print(f"Delivered in {result.response_time_ms}ms")
        elif result.is_retryable:
            print("Retry later")
        else:
            print(f"Permanent failure: {result.error_code}")
    """
    
    def __init__(self, provider: Optional[WebhookProvider] = None):
        """Initialize webhook sender.
        
        Args:
            provider: WebhookProvider implementation (defaults to MockWebhookProvider)
        """
        self.provider = provider or MockWebhookProvider()
        self.logger = logger
    
    def send(self, message: WebhookMessage) -> WebhookSendResult:
        """Send webhook notification message.
        
        Main entrypoint for webhook delivery. Handles:
        1. Message validation
        2. Provider invocation
        3. HTTP error mapping and classification
        4. Comprehensive logging
        
        Args:
            message: WebhookMessage to send
            
        Returns:
            WebhookSendResult with status, response time, and error details
        """
        try:
            # Validate message structure
            self._validate_message(message)
            
            # Send via provider
            result = self.provider.send(message)
            
            # Log result
            if result.success:
                self.logger.info(
                    f"Webhook delivered successfully",
                    extra={
                        "webhook_url": result.webhook_url[:50],
                        "http_status": result.http_status,
                        "response_time_ms": result.response_time_ms,
                        **result.metadata,
                    }
                )
            else:
                log_level = logging.WARNING if result.is_retryable else logging.ERROR
                self.logger.log(
                    log_level,
                    f"Webhook delivery failed: {result.error_message}",
                    extra={
                        "webhook_url": result.webhook_url[:50],
                        "error_code": result.error_code,
                        "is_retryable": result.is_retryable,
                        "http_status": result.http_status,
                        "response_time_ms": result.response_time_ms,
                        **result.metadata,
                    }
                )
            
            return result
            
        except RetryableWebhookError as e:
            # Retryable error from provider
            result = WebhookSendResult(
                success=False,
                status=WebhookDeliveryStatus.FAILED_RETRYABLE,
                webhook_url=message.webhook_url,
                sent_at_utc=datetime.now(tz=timezone.utc),
                http_status=e.http_status,
                error_code=e.error_code,
                error_message=str(e),
                is_retryable=True,
                metadata=message.metadata,
            )
            self.logger.warning(
                f"Retryable webhook error: {e.error_code}",
                extra={
                    "webhook_url": message.webhook_url[:50],
                    **message.metadata,
                }
            )
            return result
            
        except NonRetryableWebhookError as e:
            # Non-retryable error from provider
            result = WebhookSendResult(
                success=False,
                status=WebhookDeliveryStatus.FAILED_NON_RETRYABLE,
                webhook_url=message.webhook_url,
                sent_at_utc=datetime.now(tz=timezone.utc),
                http_status=e.http_status,
                error_code=e.error_code,
                error_message=str(e),
                is_retryable=False,
                metadata=message.metadata,
            )
            self.logger.error(
                f"Non-retryable webhook error: {e.error_code}",
                extra={
                    "webhook_url": message.webhook_url[:50],
                    **message.metadata,
                }
            )
            return result
            
        except Exception as e:
            # Unknown error - safe to retry
            result = WebhookSendResult(
                success=False,
                status=WebhookDeliveryStatus.FAILED_UNKNOWN,
                webhook_url=message.webhook_url,
                sent_at_utc=datetime.now(tz=timezone.utc),
                error_code="unknown_error",
                error_message=str(e),
                is_retryable=True,
                metadata=message.metadata,
            )
            self.logger.error(
                f"Unknown webhook error: {type(e).__name__}: {e}",
                extra={
                    "webhook_url": message.webhook_url[:50],
                    **message.metadata,
                }
            )
            return result
    
    def _validate_message(self, message: WebhookMessage) -> None:
        """Validate webhook message structure.
        
        Args:
            message: WebhookMessage to validate
            
        Raises:
            InvalidWebhookUrlError: If URL is invalid
            InvalidWebhookPayloadError: If payload is invalid
        """
        if not message.webhook_url or not isinstance(message.webhook_url, str):
            raise InvalidWebhookUrlError("'webhook_url' must be a non-empty string")
        
        if not message.webhook_url.startswith(("http://", "https://")):
            raise InvalidWebhookUrlError("'webhook_url' must start with http:// or https://")
        
        if not isinstance(message.payload, dict):
            raise InvalidWebhookPayloadError("'payload' must be a dictionary")
        
        if not message.payload:
            raise InvalidWebhookPayloadError("'payload' cannot be empty")
