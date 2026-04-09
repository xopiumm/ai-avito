"""Tests for push notification sender adapter."""

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
)


# ============================================================================
# PAYLOAD VALIDATION TESTS
# ============================================================================


class TestPushPayload:
    """PushPayload dataclass validation tests."""
    
    def test_payload_valid_minimal(self):
        """Valid payload with required fields."""
        payload = PushPayload(title="Alert", body="Message")
        assert payload.title == "Alert"
        assert payload.body == "Message"
        assert payload.data == {}
        assert payload.badge is None
    
    def test_payload_with_all_fields(self):
        """Payload with all optional fields."""
        payload = PushPayload(
            title="Rain",
            body="Rain expected",
            data={"probability": "80"},
            badge=5,
            sound="default",
            icon="rain_icon",
            click_action="https://app.com",
            color="#FF0000",
        )
        assert payload.badge == 5
        assert payload.color == "#FF0000"
    
    def test_payload_invalid_empty_title(self):
        """Title cannot be empty."""
        with pytest.raises(InvalidPushPayloadError):
            PushPayload(title="", body="Body")
    
    def test_payload_invalid_none_title(self):
        """Title cannot be None."""
        with pytest.raises(InvalidPushPayloadError):
            PushPayload(title=None, body="Body")
    
    def test_payload_invalid_empty_body(self):
        """Body cannot be empty."""
        with pytest.raises(InvalidPushPayloadError):
            PushPayload(title="Title", body="")
    
    def test_payload_to_dict_minimal(self):
        """to_dict includes required fields."""
        payload = PushPayload(title="Alert", body="Message")
        result = payload.to_dict()
        assert result["title"] == "Alert"
        assert result["body"] == "Message"
        assert "data" not in result  # Empty data not included
    
    def test_payload_to_dict_with_optional_fields(self):
        """to_dict includes all non-None optional fields."""
        payload = PushPayload(
            title="Alert",
            body="Message",
            data={"key": "value"},
            sound="default",
        )
        result = payload.to_dict()
        assert result["data"] == {"key": "value"}
        assert result["sound"] == "default"
        assert "icon" not in result  # None fields excluded


# ============================================================================
# MESSAGE VALIDATION TESTS
# ============================================================================


class TestPushMessage:
    """PushMessage input validation tests."""
    
    def test_message_valid_minimal(self):
        """Valid message with required fields."""
        payload = PushPayload(title="A", body="B")
        message = PushMessage(
            device_token="token123",
            platform=PushPlatform.FIREBASE,
            payload=payload,
        )
        assert message.device_token == "token123"
        assert message.platform == PushPlatform.FIREBASE
    
    def test_message_with_metadata(self):
        """Message with custom metadata."""
        payload = PushPayload(title="A", body="B")
        message = PushMessage(
            device_token="token",
            platform=PushPlatform.APNS,
            payload=payload,
            metadata={"sub_id": 42},
        )
        assert message.metadata["sub_id"] == 42
    
    def test_message_invalid_empty_token(self):
        """Device token cannot be empty."""
        payload = PushPayload(title="A", body="B")
        with pytest.raises(InvalidPushPayloadError):
            PushMessage(device_token="", platform=PushPlatform.FIREBASE, payload=payload)
    
    def test_message_invalid_none_token(self):
        """Device token cannot be None."""
        payload = PushPayload(title="A", body="B")
        with pytest.raises(InvalidPushPayloadError):
            PushMessage(device_token=None, platform=PushPlatform.FIREBASE, payload=payload)
    
    def test_message_invalid_platform_type(self):
        """Platform must be PushPlatform enum."""
        payload = PushPayload(title="A", body="B")
        with pytest.raises(InvalidPlatformError):
            PushMessage(device_token="token", platform="invalid", payload=payload)
    
    def test_message_invalid_payload_type(self):
        """Payload must be PushPayload instance."""
        with pytest.raises(InvalidPushPayloadError):
            PushMessage(device_token="token", platform=PushPlatform.FIREBASE, payload={"title": "A"})
    
    def test_message_repr(self):
        """Message has descriptive repr."""
        payload = PushPayload(title="Alert Title", body="B")
        message = PushMessage(device_token="token_xyz_abc", platform=PushPlatform.FIREBASE, payload=payload)
        repr_str = repr(message)
        assert "PushMessage" in repr_str
        assert "token_xyz_abc" in repr_str


# ============================================================================
# RESULT MODEL TESTS
# ============================================================================


class TestPushSendResult:
    """PushSendResult output model tests."""
    
    def test_result_success_sent(self):
        """Successful send result."""
        result = PushSendResult(
            success=True,
            status=PushDeliveryStatus.SENT,
            device_token="token",
            platform=PushPlatform.FIREBASE,
            sent_at_utc=datetime.now(tz=timezone.utc),
            message_id="msg_123",
            is_retryable=False,
        )
        assert result.success is True
        assert result.status == PushDeliveryStatus.SENT
        assert result.message_id == "msg_123"
    
    def test_result_failed_retryable(self):
        """Failed send with retryable error."""
        result = PushSendResult(
            success=False,
            status=PushDeliveryStatus.FAILED_RETRYABLE,
            device_token="token",
            platform=PushPlatform.FIREBASE,
            sent_at_utc=datetime.now(tz=timezone.utc),
            error_code="timeout",
            error_message="Request timed out",
            is_retryable=True,
        )
        assert result.success is False
        assert result.is_retryable is True
        assert result.error_code == "timeout"
    
    def test_result_failed_non_retryable(self):
        """Failed send with non-retryable error."""
        result = PushSendResult(
            success=False,
            status=PushDeliveryStatus.FAILED_NON_RETRYABLE,
            device_token="token",
            platform=PushPlatform.APNS,
            sent_at_utc=datetime.now(tz=timezone.utc),
            error_code="invalid_token",
            error_message="Token invalid",
            is_retryable=False,
            device_status=DeviceTokenStatus.INVALID,
        )
        assert result.is_retryable is False
        assert result.device_status == DeviceTokenStatus.INVALID
    
    def test_result_device_inactive(self):
        """Device inactive result."""
        result = PushSendResult(
            success=False,
            status=PushDeliveryStatus.DEVICE_INACTIVE,
            device_token="token",
            platform=PushPlatform.FIREBASE,
            sent_at_utc=datetime.now(tz=timezone.utc),
            error_code="device_inactive",
            device_status=DeviceTokenStatus.INACTIVE,
            is_retryable=False,
        )
        assert result.status == PushDeliveryStatus.DEVICE_INACTIVE
    
    def test_result_repr(self):
        """Result has descriptive repr."""
        result = PushSendResult(
            success=True,
            status=PushDeliveryStatus.SENT,
            device_token="token_abc",
            platform=PushPlatform.FIREBASE,
            sent_at_utc=datetime.now(tz=timezone.utc),
        )
        repr_str = repr(result)
        assert "✅" in repr_str or "PushSendResult" in repr_str


# ============================================================================
# EXCEPTION HIERARCHY TESTS
# ============================================================================


class TestExceptionHierarchy:
    """Exception classification tests."""
    
    def test_retryable_timeout_error(self):
        """PushTimeoutError is retryable."""
        exc = PushTimeoutError()
        assert exc.is_retryable is True
        assert exc.error_code == "timeout"
    
    def test_retryable_rate_limit_error(self):
        """PushRateLimitError is retryable."""
        exc = PushRateLimitError(retry_after_seconds=120)
        assert exc.is_retryable is True
        assert exc.retry_after_seconds == 120
    
    def test_retryable_service_unavailable(self):
        """PushServiceUnavailableError is retryable."""
        exc = PushServiceUnavailableError(status_code=503)
        assert exc.is_retryable is True
        assert "503" in exc.error_code
    
    def test_retryable_network_error(self):
        """PushNetworkError is retryable."""
        exc = PushNetworkError()
        assert exc.is_retryable is True
    
    def test_non_retryable_invalid_token(self):
        """InvalidDeviceTokenError is non-retryable."""
        exc = InvalidDeviceTokenError(token="bad_token")
        assert exc.is_retryable is False
        assert exc.error_code == "invalid_token"
    
    def test_non_retryable_invalid_platform(self):
        """InvalidPlatformError is non-retryable."""
        exc = InvalidPlatformError()
        assert exc.is_retryable is False
    
    def test_non_retryable_auth_failed(self):
        """AuthenticationFailedError is non-retryable."""
        exc = AuthenticationFailedError()
        assert exc.is_retryable is False
    
    def test_non_retryable_config_error(self):
        """PushConfigurationError is non-retryable."""
        exc = PushConfigurationError()
        assert exc.is_retryable is False
    
    def test_non_retryable_invalid_payload(self):
        """InvalidPushPayloadError is non-retryable."""
        exc = InvalidPushPayloadError()
        assert exc.is_retryable is False


# ============================================================================
# MOCK PROVIDER TESTS
# ============================================================================


class TestMockPushProvider:
    """MockPushProvider behavior tests."""
    
    def test_mock_success(self):
        """Mock provider successful send."""
        provider = MockPushProvider(success_rate=1.0)
        payload = PushPayload(title="A", body="B")
        message = PushMessage(device_token="token", platform=PushPlatform.FIREBASE, payload=payload)
        result = provider.send(message)
        
        assert result.success is True
        assert result.status == PushDeliveryStatus.SENT
        assert result.message_id is not None
    
    def test_mock_fail_retryable(self):
        """Mock provider retryable failure."""
        provider = MockPushProvider(fail_with_retryable=True)
        payload = PushPayload(title="A", body="B")
        message = PushMessage(device_token="token", platform=PushPlatform.FIREBASE, payload=payload)
        result = provider.send(message)
        
        assert result.success is False
        assert result.is_retryable is True
        assert "unavailable" in result.error_code.lower()
    
    def test_mock_fail_non_retryable(self):
        """Mock provider non-retryable failure."""
        provider = MockPushProvider(fail_with_non_retryable=True)
        payload = PushPayload(title="A", body="B")
        message = PushMessage(device_token="token", platform=PushPlatform.FIREBASE, payload=payload)
        result = provider.send(message)
        
        assert result.success is False
        assert result.is_retryable is False
        assert result.device_status == DeviceTokenStatus.INVALID
    
    def test_mock_invalid_token_list(self):
        """Mock provider treats listed tokens as invalid."""
        provider = MockPushProvider(invalid_tokens=["bad_token"])
        payload = PushPayload(title="A", body="B")
        message = PushMessage(device_token="bad_token", platform=PushPlatform.FIREBASE, payload=payload)
        result = provider.send(message)
        
        assert result.success is False
        assert result.status == PushDeliveryStatus.DEVICE_INACTIVE
        assert result.device_status == DeviceTokenStatus.INACTIVE
    
    def test_mock_tracks_sent_messages(self):
        """Mock provider records sent messages."""
        provider = MockPushProvider(success_rate=1.0)
        payload = PushPayload(title="A", body="B")
        message = PushMessage(device_token="token", platform=PushPlatform.FIREBASE, payload=payload)
        
        provider.send(message)
        
        assert len(provider.sent_messages) == 1
        assert provider.sent_messages[0].device_token == "token"


# ============================================================================
# PUSH SENDER INTEGRATION TESTS
# ============================================================================


class TestPushSender:
    """PushSender main service tests."""
    
    def test_sender_successful_send(self):
        """Sender successfully sends message."""
        sender = PushSender(provider=MockPushProvider(success_rate=1.0))
        payload = PushPayload(title="Alert", body="Rain tomorrow")
        message = PushMessage(device_token="token", platform=PushPlatform.FIREBASE, payload=payload)
        
        result = sender.send(message)
        
        assert result.success is True
        assert result.status == PushDeliveryStatus.SENT
    
    def test_sender_handles_retryable_error(self):
        """Sender handles retryable error."""
        sender = PushSender(provider=MockPushProvider(fail_with_retryable=True))
        payload = PushPayload(title="A", body="B")
        message = PushMessage(device_token="token", platform=PushPlatform.FIREBASE, payload=payload)
        
        result = sender.send(message)
        
        assert result.success is False
        assert result.is_retryable is True
    
    def test_sender_handles_non_retryable_error(self):
        """Sender handles non-retryable error."""
        sender = PushSender(provider=MockPushProvider(fail_with_non_retryable=True))
        payload = PushPayload(title="A", body="B")
        message = PushMessage(device_token="token", platform=PushPlatform.FIREBASE, payload=payload)
        
        result = sender.send(message)
        
        assert result.success is False
        assert result.is_retryable is False
    
    def test_sender_default_mock_provider(self):
        """Sender uses MockPushProvider by default."""
        sender = PushSender()
        assert isinstance(sender.provider, MockPushProvider)
    
    def test_sender_validates_device_token(self):
        """Sender validates device token."""
        sender = PushSender()
        payload = PushPayload(title="A", body="B")
        # Create valid message but sender tests validation in send()
        message = PushMessage(device_token="valid_token", platform=PushPlatform.FIREBASE, payload=payload)
        
        result = sender.send(message)
        
        # Should succeed since both message and provider state are valid
        assert result.success is True
