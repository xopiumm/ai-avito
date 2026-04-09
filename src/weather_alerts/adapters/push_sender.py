"""Push notification delivery adapter for alerts.

This module provides a flexible push notification interface that:
- Abstracts push provider details (Firebase Cloud Messaging, Apple Push, etc.)
- Distinguishes retryable from non-retryable errors
- Enables provider-agnostic implementations
- Supports device platform targeting (iOS, Android, Web)
- Handles device state management (active/inactive/invalid)

Supported features:
- Multi-platform targeting (iOS via APNs, Android via FCM, Web via FCM)
- Device token management and validation
- Structured payload with title, body, data fields
- Platform-specific formatting
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


class PushPlatform(str, PyEnum):
    """Target platform for push notifications."""
    
    FIREBASE = "firebase"              # Android + Web via Firebase Cloud Messaging
    APNS = "apns"                      # iOS via Apple Push Notification service
    HUAWEI = "huawei"                  # Huawei devices
    SAMSUNG = "samsung"                # Samsung devices (alt provider)


class PushDeliveryStatus(str, PyEnum):
    """Push notification delivery outcome status."""
    
    SENT = "sent"                          # Successfully delivered to provider
    QUEUED = "queued"                      # Accepted for delivery
    FAILED_RETRYABLE = "failed_retryable"  # Temporary error, should retry
    FAILED_NON_RETRYABLE = "failed_non_retryable"  # Permanent error, don't retry
    FAILED_UNKNOWN = "failed_unknown"      # Unknown error, safe retry allowed
    DEVICE_INACTIVE = "device_inactive"    # Device token invalid/expired
    DEVICE_NOT_FOUND = "device_not_found"  # Device token never registered


class DeviceTokenStatus(str, PyEnum):
    """State of a device token."""
    
    ACTIVE = "active"                  # Token valid and reachable
    INACTIVE = "inactive"              # Token expired or user opt-out
    INVALID = "invalid"                # Token format error
    UNREGISTERED = "unregistered"       # Device never seen
    SOFT_BOUNCE = "soft_bounce"        # Temporary delivery failure
    HARD_BOUNCE = "hard_bounce"        # Permanent delivery failure


# ============================================================================
# EXCEPTIONS: Retryable
# ============================================================================


class PushSenderException(Exception):
    """Base exception for push sending."""
    pass


class RetryablePushError(PushSenderException):
    """Temporary error that can be retried."""
    
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


class PushTimeoutError(RetryablePushError):
    """Push provider connection or request timed out."""
    
    def __init__(self, message: str = "Push provider request timed out"):
        super().__init__(message, error_code="timeout")


class PushRateLimitError(RetryablePushError):
    """Rate limit exceeded from push provider."""
    
    def __init__(self, message: str = "Push provider rate limit exceeded", retry_after_seconds: int = 60):
        super().__init__(
            message,
            error_code="rate_limit",
            retry_after_seconds=retry_after_seconds,
        )


class PushServiceUnavailableError(RetryablePushError):
    """Push service temporarily unavailable."""
    
    def __init__(self, message: str = "Push service unavailable", status_code: Optional[int] = None):
        error_code = f"service_unavailable_{status_code}" if status_code else "service_unavailable"
        super().__init__(message, error_code=error_code)


class PushNetworkError(RetryablePushError):
    """Network connectivity issue with push provider."""
    
    def __init__(self, message: str = "Network error contacting push provider"):
        super().__init__(message, error_code="network_error")


# ============================================================================
# EXCEPTIONS: Non-Retryable
# ============================================================================


class NonRetryablePushError(PushSenderException):
    """Permanent error that should NOT be retried."""
    
    def __init__(self, message: str, error_code: Optional[str] = None):
        super().__init__(message)
        self.error_code = error_code
        self.is_retryable = False


class InvalidDeviceTokenError(NonRetryablePushError):
    """Device token is invalid or rejected by provider."""
    
    def __init__(self, message: str = "Invalid device token", token: Optional[str] = None):
        super().__init__(message, error_code="invalid_token")
        self.token = token


class InvalidPlatformError(NonRetryablePushError):
    """Push platform not supported."""
    
    def __init__(self, message: str = "Invalid push platform"):
        super().__init__(message, error_code="invalid_platform")


class AuthenticationFailedError(NonRetryablePushError):
    """Push provider authentication failed."""
    
    def __init__(self, message: str = "Push provider authentication failed"):
        super().__init__(message, error_code="auth_failed")


class PushConfigurationError(NonRetryablePushError):
    """Push sender misconfigured."""
    
    def __init__(self, message: str = "Push sender configuration error"):
        super().__init__(message, error_code="config_error")


class InvalidPushPayloadError(NonRetryablePushError):
    """Push payload is invalid."""
    
    def __init__(self, message: str = "Invalid push payload"):
        super().__init__(message, error_code="invalid_payload")


# ============================================================================
# DATA MODELS
# ============================================================================


@dataclass
class PushPayload:
    """Push notification payload.
    
    Represents the content to be sent to a device.
    
    Attributes:
        title: Notification title (required)
        body: Notification body text (required)
        data: Custom data fields for app handling (key-value pairs)
        badge: Badge count to display (iOS/Android)
        sound: Sound identifier to play
        icon: Icon resource identifier
        click_action: Action URI when notification clicked
        color: Notification color in hex format
    """
    
    title: str
    body: str
    data: Dict[str, str] = field(default_factory=dict)
    badge: Optional[int] = None
    sound: Optional[str] = None
    icon: Optional[str] = None
    click_action: Optional[str] = None
    color: Optional[str] = None
    
    def __post_init__(self):
        """Validate payload structure."""
        if not self.title or not isinstance(self.title, str):
            raise InvalidPushPayloadError("'title' must be a non-empty string")
        if not self.body or not isinstance(self.body, str):
            raise InvalidPushPayloadError("'body' must be a non-empty string")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for provider."""
        result = {
            "title": self.title,
            "body": self.body,
        }
        if self.data:
            result["data"] = self.data
        if self.badge is not None:
            result["badge"] = self.badge
        if self.sound:
            result["sound"] = self.sound
        if self.icon:
            result["icon"] = self.icon
        if self.click_action:
            result["click_action"] = self.click_action
        if self.color:
            result["color"] = self.color
        return result


@dataclass
class PushMessage:
    """Input message for push sending.
    
    Represents a single push notification to be sent to a device.
    
    Attributes:
        device_token: Device token identifier
        platform: Target platform (FIREBASE, APNS, etc.)
        payload: PushPayload with notification content
        metadata: Custom metadata for tracking/debugging
    """
    
    device_token: str
    platform: PushPlatform
    payload: PushPayload
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate message structure."""
        if not self.device_token or not isinstance(self.device_token, str):
            raise InvalidPushPayloadError("'device_token' must be a non-empty string")
        if not isinstance(self.platform, PushPlatform):
            raise InvalidPlatformError(f"Invalid platform: {self.platform}")
        if not isinstance(self.payload, PushPayload):
            raise InvalidPushPayloadError("'payload' must be a PushPayload instance")
    
    def __repr__(self) -> str:
        return (
            f"<PushMessage token='{self.device_token[:20]}...' "
            f"platform={self.platform} title='{self.payload.title[:30]}...'>"
        )


@dataclass
class PushSendResult:
    """Result of push notification send operation.
    
    Attributes:
        success: Whether notification was successfully sent
        status: PushDeliveryStatus enum value
        device_token: Target device token
        platform: Push platform used
        sent_at_utc: Timestamp when send was attempted
        message_id: Provider-assigned message ID (for tracking)
        error_code: Error code if failed
        error_message: Human-readable error description
        is_retryable: Whether this error can be retried
        device_status: Updated device token status
        provider_response: Raw provider response for debugging
        metadata: Metadata passed from input message
    """
    
    success: bool
    status: PushDeliveryStatus
    device_token: str
    platform: PushPlatform
    sent_at_utc: datetime
    message_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    is_retryable: bool = False
    device_status: Optional[DeviceTokenStatus] = None
    provider_response: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __repr__(self) -> str:
        status_emoji = "✅" if self.success else "❌"
        return (
            f"{status_emoji} <PushSendResult token='{self.device_token[:20]}...' "
            f"platform={self.platform} status={self.status}>"
        )


# ============================================================================
# PROVIDER INTERFACE
# ============================================================================


class PushProvider(ABC):
    """Abstract interface for push providers.
    
    Implementations must handle:
    - Platform-specific API details (FCM, APNs, etc.)
    - Device token validation
    - Payload formatting per platform
    - HTTP error mapping
    - Device state tracking
    """
    
    @abstractmethod
    def send(self, message: PushMessage) -> PushSendResult:
        """Send push notification via provider.
        
        Args:
            message: PushMessage to send
            
        Returns:
            PushSendResult with status and details
            
        Raises:
            RetryablePushError: For temporary errors
            NonRetryablePushError: For permanent errors
        """
        pass


# ============================================================================
# MOCK PROVIDER (for testing)
# ============================================================================


class MockPushProvider(PushProvider):
    """Mock provider for testing push notifications.
    
    Simulates push sending without actual network calls.
    Supports scenarios like:
    - Successful sends
    - Device token failures (invalid/expired)
    - Simulated failures (retryable and non-retryable)
    - Configurable success rates
    """
    
    def __init__(
        self,
        success_rate: float = 1.0,      # 0.0-1.0 probability of success
        fail_with_retryable: bool = False,
        fail_with_non_retryable: bool = False,
        invalid_tokens: Optional[List[str]] = None,  # Simulate invalid tokens
    ):
        """Initialize mock provider.
        
        Args:
            success_rate: Fraction of sends that succeed
            fail_with_retryable: Always fail with retryable error
            fail_with_non_retryable: Always fail with non-retryable error
            invalid_tokens: Tokens to treat as invalid/expired
        """
        self.success_rate = success_rate
        self.fail_with_retryable = fail_with_retryable
        self.fail_with_non_retryable = fail_with_non_retryable
        self.invalid_tokens = invalid_tokens or []
        self.sent_messages: List[PushMessage] = []
    
    def send(self, message: PushMessage) -> PushSendResult:
        """Mock send implementation."""
        import random
        
        sent_at = datetime.now(tz=timezone.utc)
        self.sent_messages.append(message)
        
        # Check for invalid/expired tokens
        if message.device_token in self.invalid_tokens:
            return PushSendResult(
                success=False,
                status=PushDeliveryStatus.DEVICE_INACTIVE,
                device_token=message.device_token,
                platform=message.platform,
                sent_at_utc=sent_at,
                error_code="device_inactive",
                error_message="Device token inactive (mock)",
                is_retryable=False,
                device_status=DeviceTokenStatus.INACTIVE,
                metadata=message.metadata,
            )
        
        # Simulate configured failures
        if self.fail_with_non_retryable:
            return PushSendResult(
                success=False,
                status=PushDeliveryStatus.FAILED_NON_RETRYABLE,
                device_token=message.device_token,
                platform=message.platform,
                sent_at_utc=sent_at,
                error_code="invalid_token",
                error_message="Invalid device token (mock)",
                is_retryable=False,
                device_status=DeviceTokenStatus.INVALID,
                metadata=message.metadata,
            )
        
        if self.fail_with_retryable:
            return PushSendResult(
                success=False,
                status=PushDeliveryStatus.FAILED_RETRYABLE,
                device_token=message.device_token,
                platform=message.platform,
                sent_at_utc=sent_at,
                error_code="service_unavailable",
                error_message="Push service temporarily unavailable (mock)",
                is_retryable=True,
                metadata=message.metadata,
            )
        
        # Simulate success based on rate
        if random.random() < self.success_rate:
            return PushSendResult(
                success=True,
                status=PushDeliveryStatus.SENT,
                device_token=message.device_token,
                platform=message.platform,
                sent_at_utc=sent_at,
                message_id=f"mock_push_{sent_at.timestamp()}",
                is_retryable=False,
                device_status=DeviceTokenStatus.ACTIVE,
                metadata=message.metadata,
            )
        else:
            # Simulate random retryable error
            return PushSendResult(
                success=False,
                status=PushDeliveryStatus.FAILED_RETRYABLE,
                device_token=message.device_token,
                platform=message.platform,
                sent_at_utc=sent_at,
                error_code="timeout",
                error_message="Push request timed out (mock)",
                is_retryable=True,
                metadata=message.metadata,
            )


# ============================================================================
# MAIN PUSH SENDER SERVICE
# ============================================================================


class PushSender:
    """Main push notification sending service.
    
    Coordinates message validation, provider selection, and error handling.
    Works with any PushProvider implementation.
    
    Features:
    - Provider abstraction (Firebase, APNs, Huawei, etc.)
    - Unified error classification (retryable vs non-retryable)
    - Device token state tracking (active/inactive/invalid)
    - Message validation before sending
    - Comprehensive logging
    
    Usage:
        # Create with mock provider
        sender = PushSender(provider=MockPushProvider())
        
        # Send push notification
        payload = PushPayload(
            title="Rain Alert",
            body="Rain expected tomorrow",
            data={"alert_type": "rain", "probability": "80"},
            click_action="https://app.example.com/alerts",
        )
        message = PushMessage(
            device_token="device_token_123",
            platform=PushPlatform.FIREBASE,
            payload=payload,
            metadata={"subscription_id": 123},
        )
        result = sender.send(message)
        
        if result.success:
            print(f"Sent as {result.message_id}")
        elif result.is_retryable:
            print("Retry later")
        else:
            update_device_status(result.device_status)
    """
    
    def __init__(self, provider: Optional[PushProvider] = None):
        """Initialize push sender.
        
        Args:
            provider: PushProvider implementation (defaults to MockPushProvider)
        """
        self.provider = provider or MockPushProvider()
        self.logger = logger
    
    def send(self, message: PushMessage) -> PushSendResult:
        """Send push notification message.
        
        Main entrypoint for sending push notifications. Handles:
        1. Message validation
        2. Provider invocation
        3. Error mapping and logging
        4. Device state determination
        
        Args:
            message: PushMessage to send
            
        Returns:
            PushSendResult with status, message_id, and error details
        """
        try:
            # Validate message structure
            self._validate_message(message)
            
            # Send via provider
            result = self.provider.send(message)
            
            # Log result
            if result.success:
                self.logger.info(
                    f"Push sent successfully to device {result.device_token[:20]}...",
                    extra={
                        "message_id": result.message_id,
                        "platform": result.platform,
                        "device_token": result.device_token[:20],
                        **result.metadata,
                    }
                )
            else:
                log_level = logging.WARNING if result.is_retryable else logging.ERROR
                self.logger.log(
                    log_level,
                    f"Push send failed: {result.error_message}",
                    extra={
                        "error_code": result.error_code,
                        "is_retryable": result.is_retryable,
                        "device_status": result.device_status,
                        "platform": result.platform,
                        **result.metadata,
                    }
                )
            
            return result
            
        except RetryablePushError as e:
            # Retryable error from provider
            result = PushSendResult(
                success=False,
                status=PushDeliveryStatus.FAILED_RETRYABLE,
                device_token=message.device_token,
                platform=message.platform,
                sent_at_utc=datetime.now(tz=timezone.utc),
                error_code=e.error_code,
                error_message=str(e),
                is_retryable=True,
                metadata=message.metadata,
            )
            self.logger.warning(
                f"Retryable push error: {e.error_code}",
                extra={
                    "device_token": message.device_token[:20],
                    "platform": message.platform,
                    **message.metadata,
                }
            )
            return result
            
        except NonRetryablePushError as e:
            # Non-retryable error from provider
            result = PushSendResult(
                success=False,
                status=PushDeliveryStatus.FAILED_NON_RETRYABLE,
                device_token=message.device_token,
                platform=message.platform,
                sent_at_utc=datetime.now(tz=timezone.utc),
                error_code=e.error_code,
                error_message=str(e),
                is_retryable=False,
                device_status=DeviceTokenStatus.INVALID,
                metadata=message.metadata,
            )
            self.logger.error(
                f"Non-retryable push error: {e.error_code}",
                extra={
                    "device_token": message.device_token[:20],
                    "platform": message.platform,
                    **message.metadata,
                }
            )
            return result
            
        except Exception as e:
            # Unknown error - safe to retry
            result = PushSendResult(
                success=False,
                status=PushDeliveryStatus.FAILED_UNKNOWN,
                device_token=message.device_token,
                platform=message.platform,
                sent_at_utc=datetime.now(tz=timezone.utc),
                error_code="unknown_error",
                error_message=str(e),
                is_retryable=True,
                metadata=message.metadata,
            )
            self.logger.error(
                f"Unknown push error: {type(e).__name__}: {e}",
                extra={
                    "device_token": message.device_token[:20],
                    "platform": message.platform,
                    **message.metadata,
                }
            )
            return result
    
    def _validate_message(self, message: PushMessage) -> None:
        """Validate push message structure.
        
        Args:
            message: PushMessage to validate
            
        Raises:
            InvalidPushPayloadError: If message is invalid
        """
        if not message.device_token or not isinstance(message.device_token, str):
            raise InvalidPushPayloadError("'device_token' must be a non-empty string")
        
        if not isinstance(message.platform, PushPlatform):
            raise InvalidPlatformError(f"Invalid platform: {message.platform}")
        
        if not isinstance(message.payload, PushPayload):
            raise InvalidPushPayloadError("'payload' must be a PushPayload instance")
        
        if not message.payload.title or not isinstance(message.payload.title, str):
            raise InvalidPushPayloadError("'payload.title' must be a non-empty string")
        
        if not message.payload.body or not isinstance(message.payload.body, str):
            raise InvalidPushPayloadError("'payload.body' must be a non-empty string")
