"""Tests for webhook notification sender adapter."""

import pytest
from datetime import datetime, timezone
from src.weather_alerts.adapters.webhook_sender import (
    WebhookMessage,
    WebhookSendResult,
    WebhookSender,
    WebhookDeliveryStatus,
    WebhookHttpStatus,
    WebhookTimeoutError,
    WebhookConnectionError,
    WebhookNetworkError,
    WebhookServerError,
    WebhookServiceUnavailableError,
    WebhookRateLimitError,
    InvalidWebhookUrlError,
    AuthenticationFailedError,
    WebhookForbiddenError,
    WebhookNotFoundError,
    InvalidWebhookPayloadError,
    WebhookConfigurationError,
    RetryableWebhookError,
    NonRetryableWebhookError,
    MockWebhookProvider,
)


# ============================================================================
# MESSAGE VALIDATION TESTS
# ============================================================================


class TestWebhookMessage:
    """WebhookMessage input validation tests."""
    
    def test_message_valid_minimal(self):
        """Valid message with required fields."""
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={"alert_id": 123},
        )
        assert message.webhook_url == "https://example.com/webhook"
        assert message.payload == {"alert_id": 123}
        assert message.timeout_seconds == 30
    
    def test_message_with_custom_headers(self):
        """Message with custom HTTP headers."""
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={"alert": "test"},
            headers={"Authorization": "Bearer token123", "X-Custom": "value"},
        )
        assert message.headers["Authorization"] == "Bearer token123"
    
    def test_message_with_metadata(self):
        """Message with tracking metadata."""
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={"data": "test"},
            metadata={"subscription_id": 456, "user_id": 789},
        )
        assert message.metadata["subscription_id"] == 456
    
    def test_message_invalid_empty_url(self):
        """URL cannot be empty."""
        with pytest.raises(InvalidWebhookUrlError):
            WebhookMessage(webhook_url="", payload={"data": "test"})
    
    def test_message_invalid_none_url(self):
        """URL cannot be None."""
        with pytest.raises(InvalidWebhookUrlError):
            WebhookMessage(webhook_url=None, payload={"data": "test"})
    
    def test_message_invalid_url_scheme(self):
        """URL must start with http:// or https://."""
        with pytest.raises(InvalidWebhookUrlError):
            WebhookMessage(webhook_url="ftp://example.com/webhook", payload={"data": "test"})
    
    def test_message_invalid_payload_type(self):
        """Payload must be a dictionary."""
        with pytest.raises(InvalidWebhookPayloadError):
            WebhookMessage(webhook_url="https://example.com/webhook", payload="not a dict")
    
    def test_message_invalid_timeout_zero(self):
        """Timeout must be positive."""
        with pytest.raises(WebhookConfigurationError):
            WebhookMessage(
                webhook_url="https://example.com/webhook",
                payload={"data": "test"},
                timeout_seconds=0,
            )
    
    def test_message_repr(self):
        """Message has descriptive repr."""
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={"alert_id": 123, "severity": "high"},
        )
        repr_str = repr(message)
        assert "WebhookMessage" in repr_str
        assert "https://example.com" in repr_str


# ============================================================================
# RESULT MODEL TESTS
# ============================================================================


class TestWebhookSendResult:
    """WebhookSendResult output model tests."""
    
    def test_result_success_delivered(self):
        """Successful webhook delivery."""
        result = WebhookSendResult(
            success=True,
            status=WebhookDeliveryStatus.DELIVERED,
            webhook_url="https://example.com/webhook",
            sent_at_utc=datetime.now(tz=timezone.utc),
            http_status=200,
            response_body='{"status":"ok"}',
            response_time_ms=145,
            is_retryable=False,
        )
        assert result.success is True
        assert result.status == WebhookDeliveryStatus.DELIVERED
        assert result.http_status == 200
        assert result.response_time_ms == 145
    
    def test_result_success_accepted(self):
        """Webhook accepted asynchronously."""
        result = WebhookSendResult(
            success=True,
            status=WebhookDeliveryStatus.ACCEPTED,
            webhook_url="https://example.com/webhook",
            sent_at_utc=datetime.now(tz=timezone.utc),
            http_status=202,
            response_time_ms=78,
            is_retryable=False,
        )
        assert result.status == WebhookDeliveryStatus.ACCEPTED
        assert result.http_status == 202
    
    def test_result_failed_retryable(self):
        """Failed delivery with retryable error."""
        result = WebhookSendResult(
            success=False,
            status=WebhookDeliveryStatus.FAILED_RETRYABLE,
            webhook_url="https://example.com/webhook",
            sent_at_utc=datetime.now(tz=timezone.utc),
            http_status=503,
            error_code="service_unavailable",
            error_message="Webhook service unavailable",
            is_retryable=True,
            response_time_ms=2000,
        )
        assert result.is_retryable is True
        assert result.error_code == "service_unavailable"
    
    def test_result_failed_non_retryable(self):
        """Failed delivery with non-retryable error."""
        result = WebhookSendResult(
            success=False,
            status=WebhookDeliveryStatus.FAILED_NON_RETRYABLE,
            webhook_url="https://example.com/webhook",
            sent_at_utc=datetime.now(tz=timezone.utc),
            http_status=401,
            error_code="auth_failed",
            error_message="Authentication required",
            is_retryable=False,
        )
        assert result.is_retryable is False
        assert result.http_status == 401
    
    def test_result_timeout(self):
        """Request timed out."""
        result = WebhookSendResult(
            success=False,
            status=WebhookDeliveryStatus.TIMEOUT,
            webhook_url="https://example.com/webhook",
            sent_at_utc=datetime.now(tz=timezone.utc),
            error_code="timeout",
            error_message="Request timed out after 30 seconds",
            is_retryable=True,
            response_time_ms=30000,
        )
        assert result.response_time_ms == 30000
    
    def test_result_connection_failed(self):
        """Connection to webhook failed."""
        result = WebhookSendResult(
            success=False,
            status=WebhookDeliveryStatus.CONNECTION_FAILED,
            webhook_url="https://unreachable.example.com/webhook",
            sent_at_utc=datetime.now(tz=timezone.utc),
            error_code="connection_failed",
            error_message="Connection refused",
            is_retryable=True,
        )
        assert result.status == WebhookDeliveryStatus.CONNECTION_FAILED
    
    def test_result_repr(self):
        """Result has descriptive repr."""
        result = WebhookSendResult(
            success=True,
            status=WebhookDeliveryStatus.DELIVERED,
            webhook_url="https://example.com/webhook",
            sent_at_utc=datetime.now(tz=timezone.utc),
            http_status=200,
            response_time_ms=100,
        )
        repr_str = repr(result)
        assert "✅" in repr_str or "WebhookSendResult" in repr_str


# ============================================================================
# EXCEPTION HIERARCHY TESTS
# ============================================================================


class TestExceptionHierarchy:
    """Exception classification tests."""
    
    def test_retryable_timeout_error(self):
        """WebhookTimeoutError is retryable."""
        exc = WebhookTimeoutError(timeout_seconds=30)
        assert exc.is_retryable is True
        assert exc.error_code == "timeout"
        assert exc.timeout_seconds == 30
    
    def test_retryable_connection_error(self):
        """WebhookConnectionError is retryable."""
        exc = WebhookConnectionError()
        assert exc.is_retryable is True
        assert exc.error_code == "connection_failed"
    
    def test_retryable_network_error(self):
        """WebhookNetworkError is retryable."""
        exc = WebhookNetworkError()
        assert exc.is_retryable is True
    
    def test_retryable_server_error(self):
        """WebhookServerError is retryable."""
        exc = WebhookServerError(http_status=500)
        assert exc.is_retryable is True
        assert "500" in exc.error_code
    
    def test_retryable_service_unavailable(self):
        """WebhookServiceUnavailableError is retryable."""
        exc = WebhookServiceUnavailableError(retry_after_seconds=120)
        assert exc.is_retryable is True
        assert exc.retry_after_seconds == 120
    
    def test_retryable_rate_limit(self):
        """WebhookRateLimitError is retryable."""
        exc = WebhookRateLimitError(retry_after_seconds=60)
        assert exc.is_retryable is True
        assert exc.http_status == 429
    
    def test_non_retryable_invalid_url(self):
        """InvalidWebhookUrlError is non-retryable."""
        exc = InvalidWebhookUrlError()
        assert exc.is_retryable is False
        assert exc.error_code == "invalid_url"
    
    def test_non_retryable_auth_failed(self):
        """AuthenticationFailedError is non-retryable."""
        exc = AuthenticationFailedError()
        assert exc.is_retryable is False
        assert exc.http_status == 401
    
    def test_non_retryable_forbidden(self):
        """WebhookForbiddenError is non-retryable."""
        exc = WebhookForbiddenError()
        assert exc.is_retryable is False
        assert exc.http_status == 403
    
    def test_non_retryable_not_found(self):
        """WebhookNotFoundError is non-retryable."""
        exc = WebhookNotFoundError()
        assert exc.is_retryable is False
        assert exc.http_status == 404
    
    def test_non_retryable_invalid_payload(self):
        """InvalidWebhookPayloadError is non-retryable."""
        exc = InvalidWebhookPayloadError()
        assert exc.is_retryable is False
        assert exc.http_status == 400


# ============================================================================
# MOCK PROVIDER TESTS
# ============================================================================


class TestMockWebhookProvider:
    """MockWebhookProvider behavior tests."""
    
    def test_mock_success_200(self):
        """Mock provider successful delivery (200)."""
        provider = MockWebhookProvider(success_rate=1.0, http_status=200)
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={"alert": "test"},
        )
        result = provider.send(message)
        
        assert result.success is True
        assert result.status == WebhookDeliveryStatus.DELIVERED
        assert result.http_status == 200
    
    def test_mock_success_202(self):
        """Mock provider acceptance (202)."""
        provider = MockWebhookProvider(success_rate=1.0, http_status=202)
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={"alert": "test"},
        )
        result = provider.send(message)
        
        assert result.success is True
        assert result.status == WebhookDeliveryStatus.DELIVERED
        assert result.http_status == 202
    
    def test_mock_fail_retryable(self):
        """Mock provider retryable failure."""
        provider = MockWebhookProvider(fail_with_retryable=True)
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={"alert": "test"},
        )
        result = provider.send(message)
        
        assert result.success is False
        assert result.is_retryable is True
        assert result.http_status == 503
    
    def test_mock_fail_non_retryable(self):
        """Mock provider non-retryable failure."""
        provider = MockWebhookProvider(fail_with_non_retryable=True)
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={"alert": "test"},
        )
        result = provider.send(message)
        
        assert result.success is False
        assert result.is_retryable is False
        assert result.http_status == 400
    
    def test_mock_response_time(self):
        """Mock provider returns response time."""
        provider = MockWebhookProvider(success_rate=1.0, response_time_ms=250)
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={"alert": "test"},
        )
        result = provider.send(message)
        
        assert result.response_time_ms == 250
    
    def test_mock_tracks_sent_messages(self):
        """Mock provider records sent messages."""
        provider = MockWebhookProvider(success_rate=1.0)
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={"alert": "test"},
        )
        
        provider.send(message)
        
        assert len(provider.sent_messages) == 1
        assert provider.sent_messages[0].webhook_url == "https://example.com/webhook"


# ============================================================================
# WEBHOOK SENDER INTEGRATION TESTS
# ============================================================================


class TestWebhookSender:
    """WebhookSender main service tests."""
    
    def test_sender_successful_delivery(self):
        """Sender successfully delivers webhook."""
        sender = WebhookSender(provider=MockWebhookProvider(success_rate=1.0))
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={"alert_id": 123, "severity": "high"},
        )
        
        result = sender.send(message)
        
        assert result.success is True
        assert result.status == WebhookDeliveryStatus.DELIVERED
    
    def test_sender_handles_retryable_error(self):
        """Sender handles retryable error."""
        sender = WebhookSender(provider=MockWebhookProvider(fail_with_retryable=True))
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={"alert": "test"},
        )
        
        result = sender.send(message)
        
        assert result.success is False
        assert result.is_retryable is True
    
    def test_sender_handles_non_retryable_error(self):
        """Sender handles non-retryable error."""
        sender = WebhookSender(provider=MockWebhookProvider(fail_with_non_retryable=True))
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={"alert": "test"},
        )
        
        result = sender.send(message)
        
        assert result.success is False
        assert result.is_retryable is False
    
    def test_sender_default_mock_provider(self):
        """Sender uses MockWebhookProvider by default."""
        sender = WebhookSender()
        assert isinstance(sender.provider, MockWebhookProvider)
    
    def test_sender_validates_url(self):
        """Sender validates webhook URL."""
        # URL validation happens in __post_init__, so catch there
        with pytest.raises(InvalidWebhookUrlError):
            WebhookMessage(
                webhook_url="not-a-url",
                payload={"alert": "test"},
            )
    
    def test_sender_metadata_preservation(self):
        """Sender preserves metadata in result."""
        sender = WebhookSender(provider=MockWebhookProvider(success_rate=1.0))
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={"alert": "test"},
            metadata={"subscription_id": 456, "request_id": "req_123"},
        )
        
        result = sender.send(message)
        
        assert result.metadata["subscription_id"] == 456
        assert result.metadata["request_id"] == "req_123"
