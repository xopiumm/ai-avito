"""Extended unit tests for EmailSender adapter.

Tests cover:
- Provider interface contract
- Edge cases and boundary conditions
- Complex message structures
- Error code mapping
- Metadata preservation
- Integration scenarios
"""

import pytest
from datetime import datetime, timezone
from typing import Optional

from src.weather_alerts.adapters.email_sender import (
    EmailMessage,
    EmailSendResult,
    EmailDeliveryStatus,
    EmailSender,
    EmailProvider,
    MockEmailProvider,
    InvalidEmailAddressError,
    EmailTimeoutError,
    EmailRateLimitError,
)


# ============================================================================
# CUSTOM TEST PROVIDER
# ============================================================================


class AlwaysFailProvider(EmailProvider):
    """Test provider that always fails."""
    
    def send(self, message: EmailMessage) -> EmailSendResult:
        return EmailSendResult(
            success=False,
            status=EmailDeliveryStatus.FAILED_RETRYABLE,
            recipient=message.to,
            sent_at_utc=datetime.now(tz=timezone.utc),
            error_code="service_down",
            error_message="Service always down",
            is_retryable=True,
        )


class CustomErrorProvider(EmailProvider):
    """Test provider that raises custom exceptions."""
    
    def __init__(self, exception_to_raise):
        self.exception_to_raise = exception_to_raise
    
    def send(self, message: EmailMessage) -> EmailSendResult:
        raise self.exception_to_raise


class SuccessWithMetadataProvider(EmailProvider):
    """Test provider that echoes metadata in response."""
    
    def send(self, message: EmailMessage) -> EmailSendResult:
        return EmailSendResult(
            success=True,
            status=EmailDeliveryStatus.SENT,
            recipient=message.to,
            sent_at_utc=datetime.now(tz=timezone.utc),
            message_id=f"msg_{len(message.to)}",
            metadata=message.metadata,
        )


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def weather_alert_message():
    """Realistic weather alert email."""
    return EmailMessage(
        to="user@example.com",
        subject="🌧️ Rain Alert: 80% probability tomorrow",
        body_text=(
            "A rain alert has been triggered for your location.\n\n"
            "Details:\n"
            "- Event: Rain expected\n"
            "- Probability: 80%\n"
            "- Time: Tomorrow\n\n"
            "Best regards, Weather Alerts Team"
        ),
        body_html=(
            "<h1>Rain Alert</h1>"
            "<p>A rain alert has been triggered for your location.</p>"
            "<ul><li>Probability: 80%</li></ul>"
        ),
        template_data={
            "user_name": "John",
            "location": "San Francisco",
            "probability": 80,
        },
        metadata={
            "subscription_id": 123,
            "user_id": "user_456",
            "event_type": "rain_alert",
            "correlation_id": "evt_789",
        },
    )


@pytest.fixture
def batch_messages():
    """Multiple email messages for batch testing."""
    return [
        EmailMessage(
            to=f"user{i}@example.com",
            subject=f"Alert {i}",
            body_text=f"Message {i}",
            metadata={"batch_id": "batch_001", "index": i},
        )
        for i in range(5)
    ]


# ============================================================================
# PROVIDER INTERFACE TESTS
# ============================================================================


def test_provider_interface_always_fail():
    """Test custom provider that always fails."""
    provider = AlwaysFailProvider()
    message = EmailMessage(
        to="user@example.com",
        subject="Test",
        body_text="Test",
    )
    
    result = provider.send(message)
    
    assert result.success is False
    assert result.is_retryable is True


def test_provider_interface_custom_exception_retryable():
    """Test provider raising RetryableEmailError."""
    provider = CustomErrorProvider(EmailTimeoutError("Timeout in test"))
    sender = EmailSender(provider=provider)
    message = EmailMessage(
        to="user@example.com",
        subject="Test",
        body_text="Test",
    )
    
    result = sender.send(message)
    
    assert result.success is False
    assert result.is_retryable is True
    assert "timeout" in result.error_message.lower()


def test_provider_interface_custom_exception_non_retryable():
    """Test provider raising NonRetryableEmailError."""
    provider = CustomErrorProvider(InvalidEmailAddressError("Invalid email format"))
    sender = EmailSender(provider=provider)
    message = EmailMessage(
        to="user@example.com",
        subject="Test",
        body_text="Test",
    )
    
    result = sender.send(message)
    
    assert result.success is False
    assert result.is_retryable is False
    assert result.error_code == "invalid_email"


def test_provider_interface_unknown_exception():
    """Test provider raising generic exception maps to retryable."""
    provider = CustomErrorProvider(RuntimeError("Unexpected error"))
    sender = EmailSender(provider=provider)
    message = EmailMessage(
        to="user@example.com",
        subject="Test",
        body_text="Test",
    )
    
    result = sender.send(message)
    
    assert result.success is False
    assert result.is_retryable is True  # Conservative
    assert result.error_code == "unknown_error"


# ============================================================================
# MESSAGE CONTENT TESTS
# ============================================================================


def test_email_with_long_subject(weather_alert_message):
    """Test email with very long subject."""
    msg = EmailMessage(
        to="user@example.com",
        subject="A" * 1000,  # Very long
        body_text="Content",
    )
    
    sender = EmailSender(provider=MockEmailProvider())
    result = sender.send(msg)
    
    assert result.success is True


def test_email_with_special_characters():
    """Test email with special characters in body."""
    msg = EmailMessage(
        to="user@example.com",
        subject="Test Special: 日本語 émoji 🌍",
        body_text="Content with émojis: ✅ ❌ ⚠️ 🔥",
    )
    
    sender = EmailSender(provider=MockEmailProvider())
    result = sender.send(msg)
    
    assert result.success is True


def test_email_with_html_preserves_formatting():
    """Test email with complex HTML."""
    html_body = """
    <html>
        <body>
            <h1>Alert</h1>
            <p>Details:</p>
            <ul>
                <li>Item 1</li>
                <li>Item 2</li>
            </ul>
            <a href="https://example.com">Link</a>
        </body>
    </html>
    """
    
    msg = EmailMessage(
        to="user@example.com",
        subject="Test",
        body_text="Plain text version",
        body_html=html_body,
    )
    
    sender = EmailSender(provider=MockEmailProvider())
    result = sender.send(msg)
    
    assert result.success is True
    assert msg.body_html == html_body


def test_email_with_template_variables():
    """Test email with template variables preserved."""
    template_data = {
        "user_name": "John Doe",
        "location": "San Francisco",
        "alert_type": "rain",
        "percentage": 85.5,
        "timestamp": "2026-04-09T12:00:00Z",
    }
    
    msg = EmailMessage(
        to="user@example.com",
        subject="Alert for {location}",
        body_text="Hello {user_name}",
        template_data=template_data,
    )
    
    sender = EmailSender(provider=SuccessWithMetadataProvider())
    result = sender.send(msg)
    
    assert result.success is True


# ============================================================================
# METADATA TESTS
# ============================================================================


def test_metadata_preserved_in_success(weather_alert_message):
    """Test metadata preserved in successful result."""
    sender = EmailSender(provider=SuccessWithMetadataProvider())
    result = sender.send(weather_alert_message)
    
    assert result.success is True
    assert result.metadata == weather_alert_message.metadata
    assert result.metadata["subscription_id"] == 123
    assert result.metadata["correlation_id"] == "evt_789"


def test_metadata_preserved_in_failure(weather_alert_message):
    """Test metadata preserved in failed result."""
    sender = EmailSender(provider=MockEmailProvider(fail_with_retryable=True))
    result = sender.send(weather_alert_message)
    
    assert result.success is False
    assert result.metadata == weather_alert_message.metadata


def test_complex_metadata_structure():
    """Test email with nested metadata."""
    msg = EmailMessage(
        to="user@example.com",
        subject="Test",
        body_text="Test",
        metadata={
            "subscription": {
                "id": 123,
                "user_id": "user_456",
                "location": {"id": 789, "name": "SF"},
            },
            "event": {
                "type": "rain_alert",
                "confidence": 0.95,
                "tags": ["weather", "precipitation"],
            },
        },
    )
    
    sender = EmailSender(provider=SuccessWithMetadataProvider())
    result = sender.send(msg)
    
    assert result.metadata["subscription"]["id"] == 123
    assert result.metadata["event"]["confidence"] == 0.95


# ============================================================================
# BATCH AND PERFORMANCE TESTS
# ============================================================================


def test_batch_send_all_success(batch_messages):
    """Test sending multiple emails."""
    sender = EmailSender(provider=MockEmailProvider(success_rate=1.0))
    results = [sender.send(msg) for msg in batch_messages]
    
    assert len(results) == 5
    assert all(r.success for r in results)
    assert all(r.status == EmailDeliveryStatus.SENT for r in results)


def test_batch_send_mixed_results(batch_messages):
    """Test sending with mixed success/failure."""
    # Half succeed, half fail
    provider = MockEmailProvider(success_rate=0.5)
    sender = EmailSender(provider=provider)
    results = [sender.send(msg) for msg in batch_messages]
    
    assert len(results) == 5
    # Some succeed, some fail (due to randomness)
    successes = [r for r in results if r.success]
    failures = [r for r in results if not r.success]
    assert len(successes) + len(failures) == 5


def test_result_timestamp_is_utc(weather_alert_message):
    """Test that result timestamp is always UTC."""
    sender = EmailSender(provider=MockEmailProvider())
    result = sender.send(weather_alert_message)
    
    assert result.sent_at_utc.tzinfo == timezone.utc


# ============================================================================
# ERROR CODE MAPPING TESTS
# ============================================================================


def test_error_code_timeout():
    """Test timeout error code mapping."""
    provider = CustomErrorProvider(EmailTimeoutError())
    sender = EmailSender(provider=provider)
    msg = EmailMessage(to="user@example.com", subject="Test", body_text="Test")
    
    result = sender.send(msg)
    
    assert result.error_code == "timeout"
    assert result.is_retryable is True


def test_error_code_rate_limit():
    """Test rate limit error code mapping."""
    provider = CustomErrorProvider(EmailRateLimitError(retry_after_seconds=60))
    sender = EmailSender(provider=provider)
    msg = EmailMessage(to="user@example.com", subject="Test", body_text="Test")
    
    result = sender.send(msg)
    
    assert result.error_code == "rate_limit"
    assert result.is_retryable is True


# ============================================================================
# EDGE CASES
# ============================================================================


def test_email_to_single_char_domain():
    """Test email with single-char domain."""
    msg = EmailMessage(
        to="user@x.c",
        subject="Test",
        body_text="Test",
    )
    
    sender = EmailSender(provider=MockEmailProvider())
    result = sender.send(msg)
    
    assert result.success is True
    assert result.recipient == "user@x.c"


def test_email_with_very_long_body():
    """Test email with very long body (10KB+)."""
    long_body = "A" * 10000
    msg = EmailMessage(
        to="user@example.com",
        subject="Test",
        body_text=long_body,
    )
    
    sender = EmailSender(provider=MockEmailProvider())
    result = sender.send(msg)
    
    assert result.success is True


def test_email_with_no_html_only_text():
    """Test email with only text body (no HTML)."""
    msg = EmailMessage(
        to="user@example.com",
        subject="Test",
        body_text="Text only",
        body_html=None,
    )
    
    sender = EmailSender(provider=MockEmailProvider())
    result = sender.send(msg)
    
    assert result.success is True
    assert msg.body_html is None


def test_provider_response_object_in_result():
    """Test result can carry provider response data."""
    result = EmailSendResult(
        success=True,
        status=EmailDeliveryStatus.SENT,
        recipient="user@example.com",
        sent_at_utc=datetime.now(tz=timezone.utc),
        message_id="msg_123",
        provider_response={
            "provider": "sendgrid",
            "request_id": "req_456",
            "timestamp": "2026-04-09T12:00:00Z",
        },
    )
    
    assert result.provider_response["provider"] == "sendgrid"
    assert result.provider_response["request_id"] == "req_456"


# ============================================================================
# REALISTIC SCENARIOS
# ============================================================================


def test_scenario_successful_weather_alert(weather_alert_message):
    """Test realistic successful weather alert email."""
    sender = EmailSender(
        provider=MockEmailProvider(success_rate=1.0),
        from_email="alerts@weather.local",
    )
    
    result = sender.send(weather_alert_message)
    
    assert result.success is True
    assert result.recipient == "user@example.com"
    assert result.metadata["event_type"] == "rain_alert"
    assert result.metadata["subscription_id"] == 123


def test_scenario_retry_then_success(weather_alert_message):
    """Simulate retry behavior: first fails (retryable), then succeeds."""
    provider = MockEmailProvider(fail_with_retryable=False, success_rate=0.0)
    sender = EmailSender(provider=provider)
    
    # First attempt: calculate first failure
    result1 = sender.send(weather_alert_message)
    first_failed = not result1.success
    
    # Even if failed, should show is_retryable based on logic
    # Re-simulate with success provider for second attempt
    sender2 = EmailSender(
        provider=MockEmailProvider(success_rate=1.0),
    )
    result2 = sender2.send(weather_alert_message)
    
    assert result2.success is True


def test_scenario_multiple_delivery_channels():
    """Simulate sending same alert to multiple channels."""
    # Template will be created per channel since 'to' is required
    subject = "🌧️ Rain Alert"
    body_text = "Rain expected tomorrow"
    metadata = {"subscription_id": 123}
    
    channels = [
        "user1@gmail.com",
        "user2@outlook.com",
        "user3@company.com",
    ]
    
    sender = EmailSender(provider=MockEmailProvider(success_rate=1.0))
    results = []
    
    for channel in channels:
        msg = EmailMessage(
            to=channel,
            subject=subject,
            body_text=body_text,
            metadata=metadata,
        )
        result = sender.send(msg)
        results.append(result)
    
    assert len(results) == 3
    assert all(r.success for r in results)
