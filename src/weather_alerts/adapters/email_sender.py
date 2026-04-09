"""Email delivery adapter for notifications.

This module provides a flexible email sending interface that:
- Abstracts email provider details (SendGrid, AWS SES, SMTP, etc.)
- Distinguishes retryable from non-retryable errors
- Enables provider-agnostic implementations with fallback support
- Supports templating and structured delivery

Supported features:
- Text and HTML email bodies
- Template variables for personalization
- Provider abstraction via dependency injection
- Comprehensive error classification for retry logic
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS
# ============================================================================


class EmailDeliveryStatus(str, PyEnum):
    """Email delivery outcome status."""
    
    SENT = "sent"                          # Successfully delivered to provider
    QUEUED = "queued"                      # Accepted for delivery, retried later
    FAILED_RETRYABLE = "failed_retryable"  # Temporary error, should retry
    FAILED_NON_RETRYABLE = "failed_non_retryable"  # Permanent error, don't retry
    FAILED_UNKNOWN = "failed_unknown"      # Unknown error, safe retry allowed


# ============================================================================
# EXCEPTIONS: Retryable
# ============================================================================


class EmailSenderException(Exception):
    """Base exception for email sending."""
    pass


class RetryableEmailError(EmailSenderException):
    """Temporary error that can be retried (timeout, rate limit, service unavailable)."""
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        retry_after_seconds: Optional[int] = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.retry_after_seconds = retry_after_seconds
        self.is_retryable = True


class EmailTimeoutError(RetryableEmailError):
    """Email provider connection or request timed out."""
    
    def __init__(self, message: str = "Email provider request timed out"):
        super().__init__(message, error_code="timeout")


class EmailRateLimitError(RetryableEmailError):
    """Rate limit exceeded from email provider (429 Too Many Requests)."""
    
    def __init__(self, message: str = "Email provider rate limit exceeded", retry_after_seconds: int = 60):
        super().__init__(
            message,
            error_code="rate_limit",
            retry_after_seconds=retry_after_seconds,
        )


class EmailServiceUnavailableError(RetryableEmailError):
    """Email service temporarily unavailable (5xx error)."""
    
    def __init__(self, message: str = "Email service unavailable", status_code: Optional[int] = None):
        error_code = f"service_unavailable_{status_code}" if status_code else "service_unavailable"
        super().__init__(message, error_code=error_code)


class EmailNetworkError(RetryableEmailError):
    """Network connectivity issue with email provider."""
    
    def __init__(self, message: str = "Network error contacting email provider"):
        super().__init__(message, error_code="network_error")


# ============================================================================
# EXCEPTIONS: Non-Retryable
# ============================================================================


class NonRetryableEmailError(EmailSenderException):
    """Permanent error that should NOT be retried (invalid address, auth, config)."""
    
    def __init__(self, message: str, error_code: Optional[str] = None):
        super().__init__(message)
        self.error_code = error_code
        self.is_retryable = False


class InvalidEmailAddressError(NonRetryableEmailError):
    """Email address is invalid or rejected by provider."""
    
    def __init__(self, message: str = "Invalid email address", email: Optional[str] = None):
        super().__init__(message, error_code="invalid_email")
        self.email = email


class AuthenticationFailedError(NonRetryableEmailError):
    """Email provider authentication failed (wrong API key, expired credentials)."""
    
    def __init__(self, message: str = "Email provider authentication failed"):
        super().__init__(message, error_code="auth_failed")


class EmailSendConfigurationError(NonRetryableEmailError):
    """Email sender misconfigured (missing required fields, bad settings)."""
    
    def __init__(self, message: str = "Email sender configuration error"):
        super().__init__(message, error_code="config_error")


class InvalidEmailContentError(NonRetryableEmailError):
    """Email content is invalid (empty subject, body, etc.)."""
    
    def __init__(self, message: str = "Invalid email content"):
        super().__init__(message, error_code="invalid_content")


class ProviderRejectError(NonRetryableEmailError):
    """Email provider rejected the message (spam, policy violation, etc.)."""
    
    def __init__(self, message: str = "Email provider rejected message", reason: Optional[str] = None):
        super().__init__(message, error_code="provider_reject")
        self.reason = reason


# ============================================================================
# DATA MODELS
# ============================================================================


@dataclass
class EmailMessage:
    """Input message for email sending.
    
    Represents a single email to be sent with optional templating support.
    
    Attributes:
        to: Recipient email address(es)
        subject: Email subject line
        body_text: Plain text email body (required)
        body_html: Optional HTML email body (for rich content)
        from_email: Sender email (defaults to config)
        reply_to: Reply-to email address
        template_data: Dict of template variables for personalization
        metadata: Custom metadata for tracking/debugging
    """
    
    to: str  # recipient email address (single)
    subject: str
    body_text: str
    body_html: Optional[str] = None
    from_email: Optional[str] = None  # Uses config default if None
    reply_to: Optional[str] = None
    template_data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate message structure."""
        if not self.to or not isinstance(self.to, str):
            raise InvalidEmailContentError("'to' email must be a non-empty string")
        if not self.subject or not isinstance(self.subject, str):
            raise InvalidEmailContentError("'subject' must be a non-empty string")
        if not self.body_text or not isinstance(self.body_text, str):
            raise InvalidEmailContentError("'body_text' must be a non-empty string")
    
    def __repr__(self) -> str:
        return (
            f"<EmailMessage to='{self.to}' subject='{self.subject[:40]}...' "
            f"template_vars={len(self.template_data)} metadata={len(self.metadata)}>"
        )


@dataclass
class EmailSendResult:
    """Result of email send operation.
    
    Attributes:
        success: Whether email was successfully sent
        status: EmailDeliveryStatus enum value
        message_id: Provider-assigned message ID (for tracking)
        recipient: Email address message was sent to
        sent_at_utc: Timestamp when send was attempted
        error_code: Error code if failed (e.g., 'timeout', 'invalid_email', 'auth_failed')
        error_message: Human-readable error description
        is_retryable: Whether this error can be retried
        provider_response: Raw provider response for debugging
        metadata: Metadata passed from input message for correlation
    """
    
    success: bool
    status: EmailDeliveryStatus
    recipient: str
    sent_at_utc: datetime
    message_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    is_retryable: bool = False
    provider_response: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __repr__(self) -> str:
        status_emoji = "✅" if self.success else "❌"
        return (
            f"{status_emoji} <EmailSendResult to='{self.recipient}' "
            f"status={self.status} message_id={self.message_id}>"
        )


# ============================================================================
# PROVIDER INTERFACE
# ============================================================================


class EmailProvider(ABC):
    """Abstract interface for email providers.
    
    Implementations must handle provider-specific details:
    - API key management
    - Request formatting
    - Response parsing
    - HTTP error mapping
    
    This abstraction allows switching providers without changing caller code.
    """
    
    @abstractmethod
    def send(self, message: EmailMessage) -> EmailSendResult:
        """Send email via provider.
        
        Args:
            message: EmailMessage to send
            
        Returns:
            EmailSendResult with status and details
            
        Raises:
            RetryableEmailError: For temporary errors (timeout, rate limit, etc.)
            NonRetryableEmailError: For permanent errors (invalid address, auth, etc.)
        """
        pass


# ============================================================================
# MOCK PROVIDER (for testing and local development)
# ============================================================================


class MockEmailProvider(EmailProvider):
    """Mock provider for testing.
    
    Simulates email sending without actual network calls.
    Supports scenarios like:
    - Successful sends
    - Simulated failures (retryable and non-retryable)
    - Configurable success rates
    """
    
    def __init__(
        self,
        success_rate: float = 1.0,  # 0.0-1.0 probability of success
        fail_with_retryable: bool = False,
        fail_with_non_retryable: bool = False,
    ):
        """Initialize mock provider.
        
        Args:
            success_rate: Fraction of sends that succeed (0.0-1.0)
            fail_with_retryable: Always fail with retryable error
            fail_with_non_retryable: Always fail with non-retryable error
        """
        self.success_rate = success_rate
        self.fail_with_retryable = fail_with_retryable
        self.fail_with_non_retryable = fail_with_non_retryable
        self.sent_messages: List[EmailMessage] = []  # For testing
    
    def send(self, message: EmailMessage) -> EmailSendResult:
        """Mock send implementation."""
        import random
        
        sent_at = datetime.now(tz=timezone.utc)
        self.sent_messages.append(message)
        
        # Simulate configured failures
        if self.fail_with_non_retryable:
            return EmailSendResult(
                success=False,
                status=EmailDeliveryStatus.FAILED_NON_RETRYABLE,
                recipient=message.to,
                sent_at_utc=sent_at,
                error_code="invalid_email",
                error_message="Invalid email address (mock)",
                is_retryable=False,
                metadata=message.metadata,
            )
        
        if self.fail_with_retryable:
            return EmailSendResult(
                success=False,
                status=EmailDeliveryStatus.FAILED_RETRYABLE,
                recipient=message.to,
                sent_at_utc=sent_at,
                error_code="timeout",
                error_message="Request timed out (mock)",
                is_retryable=True,
                metadata=message.metadata,
            )
        
        # Simulate success based on rate
        if random.random() < self.success_rate:
            return EmailSendResult(
                success=True,
                status=EmailDeliveryStatus.SENT,
                recipient=message.to,
                sent_at_utc=sent_at,
                message_id=f"mock_{sent_at.timestamp()}",
                is_retryable=False,
                metadata=message.metadata,
            )
        else:
            # Simulate random retryable error
            return EmailSendResult(
                success=False,
                status=EmailDeliveryStatus.FAILED_RETRYABLE,
                recipient=message.to,
                sent_at_utc=sent_at,
                error_code="service_unavailable",
                error_message="Service temporarily unavailable (mock)",
                is_retryable=True,
                metadata=message.metadata,
            )


# ============================================================================
# MAIN EMAIL SENDER SERVICE
# ============================================================================


class EmailSender:
    """Main email sending service.
    
    Coordinates message validation, provider selection, and error handling.
    Works with any EmailProvider implementation.
    
    Features:
    - Provider abstraction (SendGrid, AWS SES, SMTP, etc.)
    - Unified error classification (retryable vs non-retryable)
    - Message validation before sending
    - Comprehensive logging
    - Provider fallback support (optional custom implementation)
    
    Usage:
        # Create with mock provider
        sender = EmailSender(provider=MockEmailProvider())
        
        # Send email
        message = EmailMessage(
            to="user@example.com",
            subject="Rain Alert",
            body_text="Rain expected tomorrow",
            metadata={"subscription_id": 123}
        )
        result = sender.send(message)
        
        if result.success:
            print(f"Sent as {result.message_id}")
        elif result.is_retryable:
            print("Retry later")
        else:
            print("Permanent error, don't retry")
    """
    
    def __init__(self, provider: Optional[EmailProvider] = None, from_email: Optional[str] = None):
        """Initialize email sender.
        
        Args:
            provider: EmailProvider implementation (defaults to MockEmailProvider)
            from_email: Default sender address (used if message.from_email is None)
        """
        self.provider = provider or MockEmailProvider()
        self.from_email = from_email or "alerts@weather-service.local"
        self.logger = logger
    
    def send(self, message: EmailMessage) -> EmailSendResult:
        """Send email message.
        
        Main entrypoint for sending emails. Handles:
        1. Message validation
        2. Default values assignment (from_email)
        3. Provider invocation
        4. Error mapping and logging
        
        Args:
            message: EmailMessage to send
            
        Returns:
            EmailSendResult with status, message_id, and error details
        """
        try:
            # Set default from_email if not provided
            if not message.from_email:
                message.from_email = self.from_email
            
            # Validate message structure
            self._validate_message(message)
            
            # Send via provider
            result = self.provider.send(message)
            
            # Log result
            if result.success:
                self.logger.info(
                    f"Email sent successfully to {result.recipient}",
                    extra={
                        "message_id": result.message_id,
                        "recipient": result.recipient,
                        **result.metadata,
                    }
                )
            else:
                log_level = logging.WARNING if result.is_retryable else logging.ERROR
                self.logger.log(
                    log_level,
                    f"Email send failed: {result.error_message}",
                    extra={
                        "error_code": result.error_code,
                        "is_retryable": result.is_retryable,
                        "recipient": result.recipient,
                        **result.metadata,
                    }
                )
            
            return result
            
        except RetryableEmailError as e:
            # Retryable error from provider
            result = EmailSendResult(
                success=False,
                status=EmailDeliveryStatus.FAILED_RETRYABLE,
                recipient=message.to,
                sent_at_utc=datetime.now(tz=timezone.utc),
                error_code=e.error_code,
                error_message=str(e),
                is_retryable=True,
                metadata=message.metadata,
            )
            self.logger.warning(
                f"Retryable email error: {e.error_code}",
                extra={"recipient": message.to, **message.metadata}
            )
            return result
            
        except NonRetryableEmailError as e:
            # Non-retryable error from provider
            result = EmailSendResult(
                success=False,
                status=EmailDeliveryStatus.FAILED_NON_RETRYABLE,
                recipient=message.to,
                sent_at_utc=datetime.now(tz=timezone.utc),
                error_code=e.error_code,
                error_message=str(e),
                is_retryable=False,
                metadata=message.metadata,
            )
            self.logger.error(
                f"Non-retryable email error: {e.error_code}",
                extra={"recipient": message.to, **message.metadata}
            )
            return result
            
        except Exception as e:
            # Unknown error - safe to retry
            result = EmailSendResult(
                success=False,
                status=EmailDeliveryStatus.FAILED_UNKNOWN,
                recipient=message.to,
                sent_at_utc=datetime.now(tz=timezone.utc),
                error_code="unknown_error",
                error_message=str(e),
                is_retryable=True,  # Conservative: retry on unknown errors
                metadata=message.metadata,
            )
            self.logger.error(
                f"Unknown email error: {type(e).__name__}: {e}",
                extra={"recipient": message.to, **message.metadata}
            )
            return result
    
    def _validate_message(self, message: EmailMessage) -> None:
        """Validate email message structure.
        
        Args:
            message: EmailMessage to validate
            
        Raises:
            InvalidEmailContentError: If message is invalid
        """
        if not message.to or not isinstance(message.to, str):
            raise InvalidEmailContentError("'to' email must be a non-empty string")
        
        if not message.subject or not isinstance(message.subject, str):
            raise InvalidEmailContentError("'subject' must be a non-empty string")
        
        if not message.body_text or not isinstance(message.body_text, str):
            raise InvalidEmailContentError("'body_text' must be a non-empty string")
        
        if message.body_html is not None and not isinstance(message.body_html, str):
            raise InvalidEmailContentError("'body_html' must be a string or None")
        
        if message.from_email and not isinstance(message.from_email, str):
            raise InvalidEmailContentError("'from_email' must be a string or None")
