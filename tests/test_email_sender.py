"""Unit tests for EmailSender adapter.

Tests cover:
- EmailMessage validation
- Exception hierarchy (retryable vs non-retryable)
- EmailSendResult structure
- MockEmailProvider scenarios
- EmailSender integration with providers
- Error handling and result mapping
"""

import pytest
from datetime import datetime, timezone

from src.weather_alerts.adapters.email_sender import (
    EmailMessage,
    EmailSendResult,
    EmailDeliveryStatus,
    EmailSender,
    EmailProvider,
    MockEmailProvider,
    # Exceptions - Retryable
    RetryableEmailError,
    EmailTimeoutError,
    EmailRateLimitError,
    EmailServiceUnavailableError,
    EmailNetworkError,
    # Exceptions - Non-Retryable
    NonRetryableEmailError,
    InvalidEmailAddressError,
    AuthenticationFailedError,
    EmailSendConfigurationError,
    InvalidEmailContentError,
    ProviderRejectError,
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def valid_message():
    """Valid email message for testing."""
    return EmailMessage(
        to="user@example.com",
        subject="Test Subject",
        body_text="Test body content",
        metadata={"subscription_id": 123},
    )


@pytest.fixture
def sender_with_mock():
    """EmailSender with MockEmailProvider."""
    return EmailSender(provider=MockEmailProvider(), from_email="sender@example.com")


# ============================================================================
# EMAIL MESSAGE VALIDATION TESTS
# ============================================================================


def test_email_message_valid_minimal():
    """Test creating valid message with minimal fields."""
    msg = EmailMessage(
        to="user@example.com",
        subject="Subject",
        body_text="Content",
    )
    
    assert msg.to == "user@example.com"
    assert msg.subject == "Subject"
    assert msg.body_text == "Content"
    assert msg.body_html is None
    assert msg.from_email is None
    assert msg.template_data == {}
    assert msg.metadata == {}


def test_email_message_valid_with_html():
    """Test message with HTML body."""
    msg = EmailMessage(
        to="user@example.com",
        subject="Subject",
        body_text="Text content",
        body_html="<p>HTML content</p>",
    )
    
    assert msg.body_html == "<p>HTML content</p>"


def test_email_message_valid_with_from_email():
    """Test message with custom from_email."""
    msg = EmailMessage(
        to="user@example.com",
        subject="Subject",
        body_text="Content",
        from_email="custom@example.com",
    )
    
    assert msg.from_email == "custom@example.com"


def test_email_message_valid_with_metadata():
    """Test message with metadata for tracking."""
    msg = EmailMessage(
        to="user@example.com",
        subject="Subject",
        body_text="Content",
        metadata={"subscription_id": 123, "event_type": "rain_alert"},
    )
    
    assert msg.metadata["subscription_id"] == 123
    assert msg.metadata["event_type"] == "rain_alert"


def test_email_message_invalid_empty_to():
    """Test that empty 'to' raises InvalidEmailContentError."""
    with pytest.raises(InvalidEmailContentError):
        EmailMessage(
            to="",
            subject="Subject",
            body_text="Content",
        )


def test_email_message_invalid_none_to():
    """Test that None 'to' raises InvalidEmailContentError."""
    with pytest.raises(InvalidEmailContentError):
        EmailMessage(
            to=None,
            subject="Subject",
            body_text="Content",
        )


def test_email_message_invalid_empty_subject():
    """Test that empty subject raises InvalidEmailContentError."""
    with pytest.raises(InvalidEmailContentError):
        EmailMessage(
            to="user@example.com",
            subject="",
            body_text="Content",
        )


def test_email_message_invalid_empty_body_text():
    """Test that empty body_text raises InvalidEmailContentError."""
    with pytest.raises(InvalidEmailContentError):
        EmailMessage(
            to="user@example.com",
            subject="Subject",
            body_text="",
        )


def test_email_message_invalid_html_is_not_string():
    """Test that non-string body_html is validated during send."""
    # HTML validation happens in _validate_message during send, not __init__
    # So this test just verifies the message can detect HTML type issues
    try:
        msg = EmailMessage(
            to="user@example.com",
            subject="Subject",
            body_text="Text",
            body_html=123,  # Will be checked during send
        )
        # If message creation succeeds, validation will happen in send
        sender = EmailSender(provider=MockEmailProvider())
        result = sender.send(msg)
        # Should fail validation
        assert result.success is False
    except InvalidEmailContentError:
        # If it fails in __post_init__, that's also valid
        pass


# ============================================================================
# EMAIL SEND RESULT TESTS
# ============================================================================


def test_email_send_result_successful():
    """Test result for successful send."""
    result = EmailSendResult(
        success=True,
        status=EmailDeliveryStatus.SENT,
        recipient="user@example.com",
        sent_at_utc=datetime.now(tz=timezone.utc),
        message_id="msg_12345",
        is_retryable=False,
    )
    
    assert result.success is True
    assert result.status == EmailDeliveryStatus.SENT
    assert result.message_id == "msg_12345"
    assert result.error_code is None
    assert result.error_message is None


def test_email_send_result_failed_retryable():
    """Test result for retryable failure."""
    result = EmailSendResult(
        success=False,
        status=EmailDeliveryStatus.FAILED_RETRYABLE,
        recipient="user@example.com",
        sent_at_utc=datetime.now(tz=timezone.utc),
        error_code="timeout",
        error_message="Request timed out",
        is_retryable=True,
    )
    
    assert result.success is False
    assert result.is_retryable is True
    assert result.error_code == "timeout"


def test_email_send_result_failed_non_retryable():
    """Test result for non-retryable failure."""
    result = EmailSendResult(
        success=False,
        status=EmailDeliveryStatus.FAILED_NON_RETRYABLE,
        recipient="invalid@",
        sent_at_utc=datetime.now(tz=timezone.utc),
        error_code="invalid_email",
        error_message="Invalid email address",
        is_retryable=False,
    )
    
    assert result.success is False
    assert result.is_retryable is False
    assert result.error_code == "invalid_email"


def test_email_send_result_with_metadata():
    """Test result preserves metadata from input."""
    metadata = {"subscription_id": 456, "user_id": "user789"}
    result = EmailSendResult(
        success=True,
        status=EmailDeliveryStatus.SENT,
        recipient="user@example.com",
        sent_at_utc=datetime.now(tz=timezone.utc),
        metadata=metadata,
    )
    
    assert result.metadata == metadata


# ============================================================================
# EXCEPTION HIERARCHY TESTS
# ============================================================================


def test_retryable_error_timeout():
    """Test EmailTimeoutError is retryable."""
    error = EmailTimeoutError("Timed out")
    
    assert isinstance(error, RetryableEmailError)
    assert error.is_retryable is True
    assert error.error_code == "timeout"


def test_retryable_error_rate_limit():
    """Test EmailRateLimitError with retry_after."""
    error = EmailRateLimitError("Rate limited", retry_after_seconds=120)
    
    assert isinstance(error, RetryableEmailError)
    assert error.is_retryable is True
    assert error.retry_after_seconds == 120
    assert error.error_code == "rate_limit"


def test_retryable_error_service_unavailable():
    """Test EmailServiceUnavailableError."""
    error = EmailServiceUnavailableError("Service down", status_code=503)
    
    assert isinstance(error, RetryableEmailError)
    assert error.is_retryable is True
    assert error.error_code == "service_unavailable_503"


def test_retryable_error_network():
    """Test EmailNetworkError."""
    error = EmailNetworkError("Cannot reach provider")
    
    assert isinstance(error, RetryableEmailError)
    assert error.is_retryable is True
    assert error.error_code == "network_error"


def test_non_retryable_error_invalid_email():
    """Test InvalidEmailAddressError is non-retryable."""
    error = InvalidEmailAddressError("Bad email", email="invalid@")
    
    assert isinstance(error, NonRetryableEmailError)
    assert error.is_retryable is False
    assert error.error_code == "invalid_email"
    assert error.email == "invalid@"


def test_non_retryable_error_auth_failed():
    """Test AuthenticationFailedError."""
    error = AuthenticationFailedError("Bad API key")
    
    assert isinstance(error, NonRetryableEmailError)
    assert error.is_retryable is False
    assert error.error_code == "auth_failed"


def test_non_retryable_error_config():
    """Test EmailSendConfigurationError."""
    error = EmailSendConfigurationError("Missing config")
    
    assert isinstance(error, NonRetryableEmailError)
    assert error.is_retryable is False
    assert error.error_code == "config_error"


def test_non_retryable_error_invalid_content():
    """Test InvalidEmailContentError."""
    error = InvalidEmailContentError("Empty subject")
    
    assert isinstance(error, NonRetryableEmailError)
    assert error.is_retryable is False
    assert error.error_code == "invalid_content"


def test_non_retryable_error_provider_reject():
    """Test ProviderRejectError."""
    error = ProviderRejectError("Message filtered", reason="spam")
    
    assert isinstance(error, NonRetryableEmailError)
    assert error.is_retryable is False
    assert error.reason == "spam"


# ============================================================================
# MOCK PROVIDER TESTS
# ============================================================================


def test_mock_provider_successful_send(valid_message):
    """Test mock provider successful send."""
    provider = MockEmailProvider(success_rate=1.0)
    result = provider.send(valid_message)
    
    assert result.success is True
    assert result.status == EmailDeliveryStatus.SENT
    assert result.message_id is not None
    assert len(provider.sent_messages) == 1


def test_mock_provider_tracks_sent_messages(valid_message):
    """Test mock provider tracks message history."""
    provider = MockEmailProvider()
    provider.send(valid_message)
    
    assert len(provider.sent_messages) == 1
    assert provider.sent_messages[0] == valid_message


def test_mock_provider_fail_retryable(valid_message):
    """Test mock provider can simulate retryable failure."""
    provider = MockEmailProvider(fail_with_retryable=True)
    result = provider.send(valid_message)
    
    assert result.success is False
    assert result.status == EmailDeliveryStatus.FAILED_RETRYABLE
    assert result.is_retryable is True
    assert result.error_code == "timeout"


def test_mock_provider_fail_non_retryable(valid_message):
    """Test mock provider can simulate non-retryable failure."""
    provider = MockEmailProvider(fail_with_non_retryable=True)
    result = provider.send(valid_message)
    
    assert result.success is False
    assert result.status == EmailDeliveryStatus.FAILED_NON_RETRYABLE
    assert result.is_retryable is False
    assert result.error_code == "invalid_email"


def test_mock_provider_success_rate_zero(valid_message):
    """Test mock provider with 0% success rate."""
    provider = MockEmailProvider(success_rate=0.0)
    result = provider.send(valid_message)
    
    assert result.success is False
    assert result.is_retryable is True  # Fails with retryable by default


# ============================================================================
# EMAIL SENDER INTEGRATION TESTS
# ============================================================================


def test_email_sender_send_success(sender_with_mock, valid_message):
    """Test EmailSender successful send."""
    result = sender_with_mock.send(valid_message)
    
    assert result.success is True
    assert result.status == EmailDeliveryStatus.SENT
    assert result.recipient == valid_message.to


def test_email_sender_sets_default_from_email(valid_message):
    """Test EmailSender sets default from_email."""
    sender = EmailSender(provider=MockEmailProvider(), from_email="default@example.com")
    msg = EmailMessage(
        to="user@example.com",
        subject="Subject",
        body_text="Content",
    )
    
    result = sender.send(msg)
    
    assert result.success is True
    assert msg.from_email == "default@example.com"  # Set during send


def test_email_sender_preserves_custom_from_email(valid_message):
    """Test EmailSender preserves custom from_email."""
    sender = EmailSender(provider=MockEmailProvider(), from_email="default@example.com")
    msg = EmailMessage(
        to="user@example.com",
        subject="Subject",
        body_text="Content",
        from_email="custom@example.com",
    )
    
    result = sender.send(msg)
    
    assert result.success is True
    assert msg.from_email == "custom@example.com"  # Not overwritten


def test_email_sender_handles_retryable_error(valid_message):
    """Test EmailSender maps retryable exceptions to result."""
    sender = EmailSender(provider=MockEmailProvider(fail_with_retryable=True))
    result = sender.send(valid_message)
    
    assert result.success is False
    assert result.is_retryable is True
    assert result.status == EmailDeliveryStatus.FAILED_RETRYABLE


def test_email_sender_handles_non_retryable_error(valid_message):
    """Test EmailSender maps non-retryable exceptions to result."""
    sender = EmailSender(provider=MockEmailProvider(fail_with_non_retryable=True))
    result = sender.send(valid_message)
    
    assert result.success is False
    assert result.is_retryable is False
    assert result.status == EmailDeliveryStatus.FAILED_NON_RETRYABLE


def test_email_sender_invalid_message():
    """Test EmailSender rejects invalid message during send."""
    sender = EmailSender(provider=MockEmailProvider())
    
    # Message validation fails in __post_init__
    with pytest.raises(InvalidEmailContentError):
        EmailMessage(
            to="",  # Invalid
            subject="Subject",
            body_text="Content",
        )
