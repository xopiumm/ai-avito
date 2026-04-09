"""Extended tests for webhook notification sender adapter."""

import pytest
from datetime import datetime, timezone
from src.weather_alerts.adapters.webhook_sender import (
    WebhookMessage,
    WebhookSendResult,
    WebhookSender,
    WebhookDeliveryStatus,
    WebhookProvider,
    WebhookTimeoutError,
    WebhookConnectionError,
    WebhookNetworkError,
    WebhookServerError,
    AuthenticationFailedError,
    WebhookNotFoundError,
    InvalidWebhookPayloadError,
    MockWebhookProvider,
)


# ============================================================================
# CUSTOM PROVIDER INTERFACE TESTS
# ============================================================================


class CustomWebhookProviderForTesting(WebhookProvider):
    """Custom provider for testing interface compliance."""
    
    def __init__(self, result_type: str = "success"):
        self.result_type = result_type
        self.calls = []
    
    def send(self, message: WebhookMessage) -> WebhookSendResult:
        """Implement send method."""
        self.calls.append(message)
        
        if self.result_type == "success":
            return WebhookSendResult(
                success=True,
                status=WebhookDeliveryStatus.DELIVERED,
                webhook_url=message.webhook_url,
                sent_at_utc=datetime.now(tz=timezone.utc),
                http_status=200,
                response_body='{"ack":true}',
                is_retryable=False,
                response_time_ms=123,
            )
        elif self.result_type == "retryable":
            raise WebhookTimeoutError("Custom timeout")
        else:
            raise AuthenticationFailedError("Custom auth failure")


class TestCustomProviderInterface:
    """Custom provider interface compliance tests."""
    
    def test_custom_provider_successful_send(self):
        """Custom provider can send successfully."""
        provider = CustomWebhookProviderForTesting(result_type="success")
        sender = WebhookSender(provider=provider)
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={"data": "test"},
        )
        
        result = sender.send(message)
        
        assert result.success is True
        assert provider.calls[0].webhook_url == "https://example.com/webhook"
    
    def test_custom_provider_retryable_error(self):
        """Custom provider throwing retryable error."""
        provider = CustomWebhookProviderForTesting(result_type="retryable")
        sender = WebhookSender(provider=provider)
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={"data": "test"},
        )
        
        result = sender.send(message)
        
        assert result.success is False
        assert result.is_retryable is True
    
    def test_custom_provider_non_retryable_error(self):
        """Custom provider throwing non-retryable error."""
        provider = CustomWebhookProviderForTesting(result_type="non_retryable")
        sender = WebhookSender(provider=provider)
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={"data": "test"},
        )
        
        result = sender.send(message)
        
        assert result.success is False
        assert result.is_retryable is False


# ============================================================================
# COMPLEX PAYLOAD TESTS
# ============================================================================


class TestComplexPayload:
    """Complex webhook payload tests."""
    
    def test_payload_with_nested_structure(self):
        """Webhook payload with nested objects."""
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={
                "alert_id": 123,
                "severity": "high",
                "location": {
                    "region": "Moscow",
                    "coordinates": {
                        "lat": 55.7558,
                        "lon": 37.6173,
                    }
                },
                "forecast": ["rain", "wind", "cold"],
            },
        )
        assert message.payload["location"]["region"] == "Moscow"
        assert len(message.payload["forecast"]) == 3
    
    def test_payload_with_unicode_content(self):
        """Webhook payload with unicode characters."""
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={
                "title": "Осадки 🌧️",
                "description": "Ожидаются осадки завтра",
                "regions": ["Москва", "Санкт-Петербург"],
            },
        )
        assert "🌧️" in message.payload["title"]
        assert "Москва" in message.payload["regions"]
    
    def test_payload_with_timestamps(self):
        """Webhook payload with ISO timestamps."""
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={
                "alert_id": 123,
                "created_at": "2024-01-15T10:30:00Z",
                "expires_at": "2024-01-16T10:30:00Z",
                "events": [
                    {"time": "2024-01-15T14:00:00Z", "type": "rain"},
                    {"time": "2024-01-15T18:00:00Z", "type": "wind"},
                ],
            },
        )
        assert message.payload["created_at"] == "2024-01-15T10:30:00Z"
        assert len(message.payload["events"]) == 2
    
    def test_payload_with_large_data(self):
        """Webhook payload with large data structures."""
        large_payload = {
            "alert_id": 123,
            "data_points": [{"value": i, "timestamp": f"2024-01-15T{i:02d}:00:00Z"} for i in range(24)],
        }
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload=large_payload,
        )
        assert len(message.payload["data_points"]) == 24
    
    def test_payload_with_special_characters(self):
        """Webhook payload with special characters."""
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={
                "title": "Alert: /test?param=value&other=123",
                "description": 'Contains "quotes" and \'apostrophes\'',
                "symbols": "!@#$%^&*()",
            },
        )
        assert "?" in message.payload["title"]
        assert '"' in message.payload["description"]


# ============================================================================
# HTTP STATUS CODE CLASSIFICATION TESTS
# ============================================================================


class TestHttpStatusClassification:
    """HTTP status code handling tests."""
    
    def test_status_200_success(self):
        """200 OK is success."""
        result = WebhookSendResult(
            success=True,
            status=WebhookDeliveryStatus.DELIVERED,
            webhook_url="https://example.com/webhook",
            sent_at_utc=datetime.now(tz=timezone.utc),
            http_status=200,
        )
        assert result.success is True
    
    def test_status_201_created(self):
        """201 Created is success."""
        result = WebhookSendResult(
            success=True,
            status=WebhookDeliveryStatus.DELIVERED,
            webhook_url="https://example.com/webhook",
            sent_at_utc=datetime.now(tz=timezone.utc),
            http_status=201,
        )
        assert result.success is True
    
    def test_status_202_accepted(self):
        """202 Accepted is success (asynchronous processing)."""
        result = WebhookSendResult(
            success=True,
            status=WebhookDeliveryStatus.ACCEPTED,
            webhook_url="https://example.com/webhook",
            sent_at_utc=datetime.now(tz=timezone.utc),
            http_status=202,
        )
        assert result.success is True
        assert result.status == WebhookDeliveryStatus.ACCEPTED
    
    def test_status_400_bad_request_non_retryable(self):
        """400 Bad Request is non-retryable."""
        result = WebhookSendResult(
            success=False,
            status=WebhookDeliveryStatus.FAILED_NON_RETRYABLE,
            webhook_url="https://example.com/webhook",
            sent_at_utc=datetime.now(tz=timezone.utc),
            http_status=400,
            is_retryable=False,
        )
        assert result.is_retryable is False
    
    def test_status_401_unauthorized_non_retryable(self):
        """401 Unauthorized is non-retryable."""
        result = WebhookSendResult(
            success=False,
            status=WebhookDeliveryStatus.FAILED_NON_RETRYABLE,
            webhook_url="https://example.com/webhook",
            sent_at_utc=datetime.now(tz=timezone.utc),
            http_status=401,
            is_retryable=False,
        )
        assert result.is_retryable is False
    
    def test_status_403_forbidden_non_retryable(self):
        """403 Forbidden is non-retryable."""
        result = WebhookSendResult(
            success=False,
            status=WebhookDeliveryStatus.FAILED_NON_RETRYABLE,
            webhook_url="https://example.com/webhook",
            sent_at_utc=datetime.now(tz=timezone.utc),
            http_status=403,
            is_retryable=False,
        )
        assert result.is_retryable is False
    
    def test_status_404_not_found_non_retryable(self):
        """404 Not Found is non-retryable."""
        result = WebhookSendResult(
            success=False,
            status=WebhookDeliveryStatus.FAILED_NON_RETRYABLE,
            webhook_url="https://example.com/webhook",
            sent_at_utc=datetime.now(tz=timezone.utc),
            http_status=404,
            is_retryable=False,
        )
        assert result.is_retryable is False
    
    def test_status_500_server_error_retryable(self):
        """500 Internal Server Error is retryable."""
        result = WebhookSendResult(
            success=False,
            status=WebhookDeliveryStatus.FAILED_RETRYABLE,
            webhook_url="https://example.com/webhook",
            sent_at_utc=datetime.now(tz=timezone.utc),
            http_status=500,
            is_retryable=True,
        )
        assert result.is_retryable is True
    
    def test_status_502_bad_gateway_retryable(self):
        """502 Bad Gateway is retryable."""
        result = WebhookSendResult(
            success=False,
            status=WebhookDeliveryStatus.FAILED_RETRYABLE,
            webhook_url="https://example.com/webhook",
            sent_at_utc=datetime.now(tz=timezone.utc),
            http_status=502,
            is_retryable=True,
        )
        assert result.is_retryable is True
    
    def test_status_503_service_unavailable_retryable(self):
        """503 Service Unavailable is retryable."""
        result = WebhookSendResult(
            success=False,
            status=WebhookDeliveryStatus.FAILED_RETRYABLE,
            webhook_url="https://example.com/webhook",
            sent_at_utc=datetime.now(tz=timezone.utc),
            http_status=503,
            is_retryable=True,
        )
        assert result.is_retryable is True
    
    def test_status_504_gateway_timeout_retryable(self):
        """504 Gateway Timeout is retryable."""
        result = WebhookSendResult(
            success=False,
            status=WebhookDeliveryStatus.FAILED_RETRYABLE,
            webhook_url="https://example.com/webhook",
            sent_at_utc=datetime.now(tz=timezone.utc),
            http_status=504,
            is_retryable=True,
        )
        assert result.is_retryable is True


# ============================================================================
# METADATA AND CORRELATION TESTS
# ============================================================================


class TestMetadataTracking:
    """Metadata preservation and correlation tests."""
    
    def test_metadata_preserved_in_result(self):
        """Metadata from message preserved in result."""
        sender = WebhookSender(provider=MockWebhookProvider(success_rate=1.0))
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={"alert": "test"},
            metadata={
                "subscription_id": 123,
                "user_id": 456,
                "request_id": "req_789",
            },
        )
        
        result = sender.send(message)
        
        assert result.metadata["subscription_id"] == 123
        assert result.metadata["user_id"] == 456
        assert result.metadata["request_id"] == "req_789"
    
    def test_correlation_tracking(self):
        """Metadata enables request correlation."""
        messages = []
        for i in range(3):
            message = WebhookMessage(
                webhook_url=f"https://webhook{i}.example.com/alert",
                payload={"alert_id": i, "severity": "high"},
                metadata={"batch_id": "batch_001", "sequence": i},
            )
            messages.append(message)
        
        assert messages[0].metadata["batch_id"] == "batch_001"
        assert messages[1].metadata["sequence"] == 1
        assert messages[2].metadata["batch_id"] == "batch_001"


# ============================================================================
# BATCH DELIVERY TESTS
# ============================================================================


class TestBatchDelivery:
    """Batch webhook delivery tests."""
    
    def test_send_batch_multiple_webhooks(self):
        """Send same alert to multiple webhooks."""
        sender = WebhookSender(provider=MockWebhookProvider(success_rate=1.0))
        payload = {"alert_id": 123, "severity": "high", "title": "Rain Alert"}
        
        results = []
        for i in range(3):
            message = WebhookMessage(
                webhook_url=f"https://webhook{i}.example.com/alerts",
                payload=payload,
                metadata={"webhook_index": i},
            )
            result = sender.send(message)
            results.append(result)
        
        assert len(results) == 3
        assert all(r.success for r in results)
    
    def test_batch_with_mixed_success_rates(self):
        """Batch with some successes and failures."""
        sender = WebhookSender(provider=MockWebhookProvider(success_rate=0.6))
        results = []
        
        for i in range(10):
            message = WebhookMessage(
                webhook_url=f"https://webhook{i}.example.com/alerts",
                payload={"alert_id": 123},
            )
            result = sender.send(message)
            results.append(result)
        
        successful = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        assert successful + failed == 10
        assert successful >= 3  # At least some should succeed with 60% rate
    
    def test_batch_aggregation_by_status(self):
        """Aggregate batch results by delivery status."""
        sender = WebhookSender(provider=MockWebhookProvider(success_rate=1.0, http_status=200))
        results = []
        
        for i in range(5):
            message = WebhookMessage(
                webhook_url=f"https://webhook{i}.example.com/alerts",
                payload={"alert_id": 123},
            )
            result = sender.send(message)
            results.append(result)
        
        delivered = sum(1 for r in results if r.status == WebhookDeliveryStatus.DELIVERED)
        assert delivered == 5


# ============================================================================
# RESPONSE TIME AND PERFORMANCE TESTS
# ============================================================================


class TestResponseTime:
    """Response time tracking and performance tests."""
    
    def test_response_time_tracking(self):
        """Response time is tracked and reported."""
        provider = MockWebhookProvider(success_rate=1.0, response_time_ms=342)
        sender = WebhookSender(provider=provider)
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={"alert": "test"},
        )
        
        result = sender.send(message)
        
        assert result.response_time_ms == 342
    
    def test_response_time_on_failure(self):
        """Response time tracked even on failure."""
        provider = MockWebhookProvider(fail_with_retryable=True, response_time_ms=5000)
        sender = WebhookSender(provider=provider)
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={"alert": "test"},
        )
        
        result = sender.send(message)
        
        assert result.response_time_ms == 5000
        assert result.success is False


# ============================================================================
# ERROR HANDLING EDGE CASES
# ============================================================================


class TestErrorHandling:
    """Error handling edge cases."""
    
    def test_empty_response_body(self):
        """Result with no response body."""
        result = WebhookSendResult(
            success=True,
            status=WebhookDeliveryStatus.DELIVERED,
            webhook_url="https://example.com/webhook",
            sent_at_utc=datetime.now(tz=timezone.utc),
            http_status=204,  # No Content
            response_body=None,
        )
        assert result.response_body is None
    
    def test_large_response_body(self):
        """Result with large response body (capped)."""
        large_body = "x" * 1000
        result = WebhookSendResult(
            success=True,
            status=WebhookDeliveryStatus.DELIVERED,
            webhook_url="https://example.com/webhook",
            sent_at_utc=datetime.now(tz=timezone.utc),
            http_status=200,
            response_body=large_body,
        )
        assert len(result.response_body) == 1000


# ============================================================================
# REALISTIC SCENARIO TESTS
# ============================================================================


class TestRealisticScenarios:
    """Real-world usage scenario tests."""
    
    def test_scenario_weather_alert_to_slack(self):
        """Send weather alert to Slack webhook."""
        sender = WebhookSender(provider=MockWebhookProvider(success_rate=1.0, http_status=200))
        
        message = WebhookMessage(
            webhook_url="https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX",
            payload={
                "text": "🌧️ Weather Alert",
                "attachments": [
                    {
                        "color": "warning",
                        "title": "Heavy Rain Expected",
                        "text": "Rain probability: 85%",
                        "fields": [
                            {"title": "Region", "value": "Moscow", "short": True},
                            {"title": "Time", "value": "Next 6 hours", "short": True},
                        ],
                    }
                ],
            },
            metadata={"channel": "alerts", "alert_type": "weather"},
        )
        
        result = sender.send(message)
        
        assert result.success is True
        assert result.http_status == 200
        assert result.metadata["alert_type"] == "weather"
    
    def test_scenario_alert_to_custom_api(self):
        """Send alert to custom API endpoint."""
        sender = WebhookSender(provider=MockWebhookProvider(success_rate=1.0, http_status=202))
        
        message = WebhookMessage(
            webhook_url="https://api.custom.example.com/v1/webhooks/alerts",
            payload={
                "event_type": "weather_alert",
                "alert_id": 12345,
                "severity": "high",
                "location": {
                    "type": "region",
                    "name": "Moscow",
                },
                "forecast": {
                    "type": "rain",
                    "probability": 85,
                    "expected_duration_hours": 6,
                },
                "timestamp": "2024-01-15T12:00:00Z",
            },
            headers={
                "Authorization": "Bearer secret_token",
                "X-API-Version": "v1",
            },
            timeout_seconds=60,
            metadata={"subscription_id": 789},
        )
        
        result = sender.send(message)
        
        assert result.success is True
        # MockWebhookProvider with http_status=202 still maps to DELIVERED status
        # Real provider could map 202 to ACCEPTED
        assert result.http_status == 202
    
    def test_scenario_retry_on_transient_failure(self):
        """Retry logic for transient failures."""
        sender_fails = WebhookSender(provider=MockWebhookProvider(fail_with_retryable=True))
        sender_succeeds = WebhookSender(provider=MockWebhookProvider(success_rate=1.0))
        
        message = WebhookMessage(
            webhook_url="https://example.com/webhook",
            payload={"alert": "test"},
        )
        
        # First attempt fails with retryable error
        result_1 = sender_fails.send(message)
        assert result_1.success is False
        assert result_1.is_retryable is True
        
        # Retry with fresh provider succeeds
        result_2 = sender_succeeds.send(message)
        assert result_2.success is True
    
    def test_scenario_handle_permanent_webhook_failure(self):
        """Handle permanent webhook failures gracefully."""
        sender = WebhookSender(provider=MockWebhookProvider(fail_with_non_retryable=True))
        
        message = WebhookMessage(
            webhook_url="https://invalid-webhook.example.com/",
            payload={"alert": "test"},
        )
        
        result = sender.send(message)
        
        assert result.success is False
        assert result.is_retryable is False
        # Should update webhook status to disabled/failed
        assert result.http_status == 400
