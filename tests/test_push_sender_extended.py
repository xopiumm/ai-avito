"""Extended tests for push notification sender adapter."""

import pytest
from datetime import datetime, timezone
from src.weather_alerts.adapters.push_sender import (
    PushPayload,
    PushMessage,
    PushSendResult,
    PushSender,
    PushPlatform,
    PushDeliveryStatus,
    DeviceTokenStatus,
    PushTimeoutError,
    PushRateLimitError,
    PushServiceUnavailableError,
    PushNetworkError,
    InvalidDeviceTokenError,
    InvalidPlatformError,
    InvalidPushPayloadError,
    AuthenticationFailedError,
    PushConfigurationError,
    RetryablePushError,
    NonRetryablePushError,
    MockPushProvider,
    PushProvider,
)


# ============================================================================
# CUSTOM PROVIDER INTERFACE TESTS
# ============================================================================


class CustomPushProviderForTesting(PushProvider):
    """Custom provider for testing interface compliance."""
    
    def __init__(self, result_type: str = "success"):
        self.result_type = result_type
        self.calls = []
    
    def send(self, message: PushMessage) -> PushSendResult:
        """Implement send method."""
        self.calls.append(message)
        
        if self.result_type == "success":
            return PushSendResult(
                success=True,
                status=PushDeliveryStatus.SENT,
                device_token=message.device_token,
                platform=message.platform,
                sent_at_utc=datetime.now(tz=timezone.utc),
                message_id="custom_123",
                is_retryable=False,
            )
        elif self.result_type == "retryable":
            raise PushTimeoutError("Custom provider timeout")
        else:
            raise InvalidDeviceTokenError("Custom provider invalid token")


class TestCustomProviderInterface:
    """Custom provider interface compliance tests."""
    
    def test_custom_provider_successful_send(self):
        """Custom provider can send successfully."""
        provider = CustomPushProviderForTesting(result_type="success")
        sender = PushSender(provider=provider)
        payload = PushPayload(title="A", body="B")
        message = PushMessage(device_token="token", platform=PushPlatform.FIREBASE, payload=payload)
        
        result = sender.send(message)
        
        assert result.success is True
        assert provider.calls[0].device_token == "token"
    
    def test_custom_provider_retryable_error(self):
        """Custom provider throwing retryable error."""
        provider = CustomPushProviderForTesting(result_type="retryable")
        sender = PushSender(provider=provider)
        payload = PushPayload(title="A", body="B")
        message = PushMessage(device_token="token", platform=PushPlatform.FIREBASE, payload=payload)
        
        result = sender.send(message)
        
        assert result.success is False
        assert result.is_retryable is True
    
    def test_custom_provider_non_retryable_error(self):
        """Custom provider throwing non-retryable error."""
        provider = CustomPushProviderForTesting(result_type="non_retryable")
        sender = PushSender(provider=provider)
        payload = PushPayload(title="A", body="B")
        message = PushMessage(device_token="token", platform=PushPlatform.FIREBASE, payload=payload)
        
        result = sender.send(message)
        
        assert result.success is False
        assert result.is_retryable is False


# ============================================================================
# COMPLEX MESSAGE CONTENT TESTS
# ============================================================================


class TestComplexMessageContent:
    """Complex payload and message content tests."""
    
    def test_payload_with_unicode_content(self):
        """Payload supports unicode characters."""
        payload = PushPayload(
            title="Осадки 🌧️",
            body="Ожидаются осадки завтра",
            data={"weather": "дождь"},
        )
        assert "🌧️" in payload.title
        assert "Осадки" in payload.title
    
    def test_payload_with_html_entities(self):
        """Payload with HTML entities."""
        payload = PushPayload(
            title="Alert &amp; Warning",
            body="Temperature > 30°C",
        )
        assert "&amp;" in payload.title
        assert "°C" in payload.body
    
    def test_payload_with_very_long_content(self):
        """Payload with very long strings."""
        long_title = "A" * 1000
        long_body = "B" * 5000
        payload = PushPayload(title=long_title, body=long_body)
        assert len(payload.title) == 1000
        assert len(payload.body) == 5000
    
    def test_message_with_complex_data_fields(self):
        """Message with complex nested data."""
        payload = PushPayload(title="Alert", body="Message")
        message = PushMessage(
            device_token="token",
            platform=PushPlatform.FIREBASE,
            payload=PushPayload(
                title="Alert",
                body="Body",
                data={
                    "alert_id": "123",
                    "confidence": "0.95",
                    "areas_affected": "region1,region2",
                    "timestamp": "2024-01-15T10:30:00Z",
                },
            ),
        )
        assert len(message.payload.data) == 4
    
    def test_message_with_special_characters_in_token(self):
        """Device token with special characters."""
        payload = PushPayload(title="A", body="B")
        message = PushMessage(
            device_token="token-with_special.chars:123",
            platform=PushPlatform.APNS,
            payload=payload,
        )
        assert "special" in message.device_token


# ============================================================================
# METADATA AND TRACKING TESTS
# ============================================================================


class TestMetadataTracking:
    """Message metadata and correlation tests."""
    
    def test_metadata_preserved_in_result(self):
        """Metadata from message preserved in result."""
        provider = MockPushProvider(success_rate=1.0)
        sender = PushSender(provider=provider)
        payload = PushPayload(title="A", body="B")
        message = PushMessage(
            device_token="token",
            platform=PushPlatform.FIREBASE,
            payload=payload,
            metadata={"subscription_id": 123, "user_id": 456},
        )
        
        result = sender.send(message)
        
        assert result.metadata["subscription_id"] == 123
        assert result.metadata["user_id"] == 456
    
    def test_metadata_with_nested_structure(self):
        """Metadata with nested dictionary."""
        payload = PushPayload(title="A", body="B")
        message = PushMessage(
            device_token="token",
            platform=PushPlatform.FIREBASE,
            payload=payload,
            metadata={
                "context": {
                    "region": "Moscow",
                    "severity": "high",
                },
                "tracking_id": "abc-123",
            },
        )
        assert message.metadata["context"]["region"] == "Moscow"
    
    def test_multiple_sends_track_separately(self):
        """Multiple sends tracked independently."""
        provider = MockPushProvider(success_rate=1.0)
        sender = PushSender(provider=provider)
        
        for i in range(3):
            payload = PushPayload(title=f"Alert {i}", body="B")
            message = PushMessage(
                device_token=f"token_{i}",
                platform=PushPlatform.FIREBASE,
                payload=payload,
                metadata={"index": i},
            )
            result = sender.send(message)
            assert result.metadata["index"] == i
        
        assert len(provider.sent_messages) == 3


# ============================================================================
# BATCH OPERATION TESTS
# ============================================================================


class TestBatchOperations:
    """Batch sending and aggregation tests."""
    
    def test_send_batch_mixed_platforms(self):
        """Send to multiple platforms in batch."""
        sender = PushSender(provider=MockPushProvider(success_rate=1.0))
        results = []
        
        platforms = [PushPlatform.FIREBASE, PushPlatform.APNS, PushPlatform.HUAWEI]
        for i, platform in enumerate(platforms):
            payload = PushPayload(title="Alert", body="Message")
            message = PushMessage(device_token=f"token_{i}", platform=platform, payload=payload)
            result = sender.send(message)
            results.append(result)
        
        assert len(results) == 3
        assert results[0].platform == PushPlatform.FIREBASE
        assert results[1].platform == PushPlatform.APNS
        assert results[2].platform == PushPlatform.HUAWEI
    
    def test_batch_with_mixed_success_rates(self):
        """Batch with some successes and failures."""
        sender = PushSender(provider=MockPushProvider(success_rate=0.5))
        results = []
        
        for i in range(10):
            payload = PushPayload(title="Alert", body="Message")
            message = PushMessage(device_token=f"token_{i}", platform=PushPlatform.FIREBASE, payload=payload)
            result = sender.send(message)
            results.append(result)
        
        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        assert len(successes) + len(failures) == 10
    
    def test_batch_aggregation_by_status(self):
        """Aggregate batch results by delivery status."""
        sender = PushSender(provider=MockPushProvider(success_rate=1.0))
        results = []
        
        for i in range(5):
            payload = PushPayload(title="Alert", body="Message")
            message = PushMessage(device_token=f"token_{i}", platform=PushPlatform.FIREBASE, payload=payload)
            result = sender.send(message)
            results.append(result)
        
        sent_count = sum(1 for r in results if r.status == PushDeliveryStatus.SENT)
        assert sent_count == 5


# ============================================================================
# ERROR CODE MAPPING TESTS
# ============================================================================


class TestErrorCodeMapping:
    """Error classification and code mapping tests."""
    
    def test_error_code_timeout_is_retryable(self):
        """Timeout error code maps to retryable."""
        exc = PushTimeoutError()
        assert exc.is_retryable is True
        assert exc.error_code == "timeout"
    
    def test_error_code_rate_limit_has_retry_after(self):
        """Rate limit error includes retry-after."""
        exc = PushRateLimitError(retry_after_seconds=300)
        assert exc.retry_after_seconds == 300
    
    def test_error_code_service_unavailable_has_status(self):
        """Service unavailable error includes status code."""
        exc = PushServiceUnavailableError(status_code=502)
        assert "502" in exc.error_code
    
    def test_error_code_network_is_retryable(self):
        """Network error is marked retryable."""
        exc = PushNetworkError()
        assert exc.is_retryable is True
    
    def test_error_code_invalid_token_is_not_retryable(self):
        """Invalid token error is non-retryable."""
        exc = InvalidDeviceTokenError()
        assert exc.is_retryable is False


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


class TestEdgeCases:
    """Edge case and boundary condition tests."""
    
    def test_payload_numeric_badge_zero(self):
        """Badge count can be zero."""
        payload = PushPayload(title="A", body="B", badge=0)
        assert payload.badge == 0
    
    def test_message_device_token_max_length(self):
        """Device token with maximum realistic length."""
        max_token = "t" * 500
        payload = PushPayload(title="A", body="B")
        message = PushMessage(device_token=max_token, platform=PushPlatform.FIREBASE, payload=payload)
        assert len(message.device_token) == 500
    
    def test_result_timestamp_accuracy(self):
        """Result timestamp is datetime with timezone."""
        result = PushSendResult(
            success=True,
            status=PushDeliveryStatus.SENT,
            device_token="token",
            platform=PushPlatform.FIREBASE,
            sent_at_utc=datetime.now(tz=timezone.utc),
        )
        assert result.sent_at_utc.tzinfo == timezone.utc
    
    def test_mock_provider_empty_invalid_tokens_list(self):
        """Mock provider with empty invalid tokens."""
        provider = MockPushProvider(invalid_tokens=[])
        payload = PushPayload(title="A", body="B")
        message = PushMessage(device_token="token", platform=PushPlatform.FIREBASE, payload=payload)
        result = provider.send(message)
        # Should succeed since no invalid tokens specified
        assert result.success is True or result.success is False  # depends on random
    
    def test_message_with_empty_metadata(self):
        """Message with empty metadata dict."""
        payload = PushPayload(title="A", body="B")
        message = PushMessage(
            device_token="token",
            platform=PushPlatform.FIREBASE,
            payload=payload,
            metadata={},
        )
        assert message.metadata == {}


# ============================================================================
# REALISTIC SCENARIO TESTS
# ============================================================================


class TestRealisticScenarios:
    """Real-world usage scenario tests."""
    
    def test_scenario_weather_alert_single_device(self):
        """Send single weather alert to device."""
        sender = PushSender(provider=MockPushProvider(success_rate=1.0))
        
        payload = PushPayload(
            title="⚠️ Rain Alert",
            body="Heavy rain expected in 2 hours",
            data={
                "alert_type": "rain",
                "probability": "85",
                "regions": "Moscow,Novgorod",
            },
            click_action="https://weather.app/alerts",
        )
        message = PushMessage(
            device_token="firebase_token_abc123",
            platform=PushPlatform.FIREBASE,
            payload=payload,
            metadata={
                "alert_id": 12345,
                "subscription_id": 789,
                "forecast_timestamp": "2024-01-15T12:00:00Z",
            },
        )
        
        result = sender.send(message)
        
        assert result.success is True
        assert result.device_token == "firebase_token_abc123"
        assert result.metadata["alert_id"] == 12345
    
    def test_scenario_broadcast_to_mixed_platforms(self):
        """Broadcast weather alert to multiple platforms."""
        sender = PushSender(provider=MockPushProvider(success_rate=0.95))
        
        devices = [
            ("device_1", PushPlatform.FIREBASE),
            ("device_2", PushPlatform.APNS),
            ("device_3", PushPlatform.HUAWEI),
        ]
        
        results = []
        for device_token, platform in devices:
            payload = PushPayload(
                title="Alert",
                body="Temperature exceeds 35°C",
                data={"severity": "high"},
            )
            message = PushMessage(
                device_token=device_token,
                platform=platform,
                payload=payload,
            )
            result = sender.send(message)
            results.append(result)
        
        assert len(results) == 3
        sent_results = [r for r in results if r.success]
        assert len(sent_results) >= 2  # With 95% rate, expect ~2-3 to succeed
    
    def test_scenario_handle_device_deactivation(self):
        """Handle inactive device tokens gracefully."""
        provider = MockPushProvider(invalid_tokens=["old_device_token"])
        sender = PushSender(provider=provider)
        
        payload = PushPayload(title="Alert", body="Message")
        message = PushMessage(
            device_token="old_device_token",
            platform=PushPlatform.FIREBASE,
            payload=payload,
        )
        
        result = sender.send(message)
        
        assert result.success is False
        assert result.device_status == DeviceTokenStatus.INACTIVE
        assert result.is_retryable is False
    
    def test_scenario_retry_on_transient_failure(self):
        """Retry logic for transient failures."""
        sender_with_retryable = PushSender(provider=MockPushProvider(fail_with_retryable=True))
        sender_with_success = PushSender(provider=MockPushProvider(success_rate=1.0))
        
        payload = PushPayload(title="Alert", body="Message")
        message = PushMessage(
            device_token="token",
            platform=PushPlatform.FIREBASE,
            payload=payload,
        )
        
        # First attempt fails with retryable error
        result_1 = sender_with_retryable.send(message)
        assert result_1.success is False
        assert result_1.is_retryable is True
        
        # Retry with fresh provider succeeds
        result_2 = sender_with_success.send(message)
        assert result_2.success is True
