"""Delivery retry tasks for Weather Alerts with exponential backoff strategy.

This module provides Celery tasks for delivering notifications through email, push,
and webhook channels with robust retry logic:

- Retryable errors → exponential backoff retry
- Non-retryable errors → immediate final failure
- Channel isolation: one channel failure doesn't block others
- Detailed delivery logging for monitoring

Supported channels:
  - email: via EmailSender adapter
  - push: via PushSender adapter  
  - webhook: via WebhookSender adapter

Error handling:
  - RetryableError + attempts_left → reschedule with backoff
  - RetryableError + attempts_exhausted → log as failed
  - NonRetryableError → skip retries, log as failed
  - Unknown error → retry (safe default for transient issues)
"""

import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from celery import Task, current_task
from celery.exceptions import SoftTimeLimitExceeded

from src.weather_alerts.config.settings import get_settings
from src.weather_alerts.workers.celery_app import app

# Import delivery adapters and their exceptions
from src.weather_alerts.adapters.email_sender import (
    RetryableEmailError,
    NonRetryableEmailError,
    EmailSenderException,
)
from src.weather_alerts.adapters.push_sender import (
    RetryablePushError,
    NonRetryablePushError,
    PushSenderException,
)
from src.weather_alerts.adapters.webhook_sender import (
    RetryableWebhookError,
    NonRetryableWebhookError,
    WebhookSenderException,
)

logger = logging.getLogger(__name__)


# ============================================================================
# DELIVERY TASK PAYLOAD STRUCTURE
# ============================================================================


class DeliveryTaskPayload:
    """Structured payload for delivery tasks.
    
    Attributes:
        channel: Delivery channel (email, push, webhook)
        recipient_id: User ID or endpoint identifier
        subscription_id: Associated subscription ID
        event_type: Weather event type (rain, temperature_drop, etc.)
        message_id: Unique message identifier for deduplication
        content: Delivery content (email body, push title+body, webhook payload)
        metadata: Additional context for retry and logging
        attempt_number: Current attempt (1-based)
        max_attempts: Maximum retry attempts
    """
    
    def __init__(
        self,
        channel: str,
        recipient_id: str,
        subscription_id: str,
        event_type: str,
        message_id: str,
        content: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        attempt_number: int = 1,
        max_attempts: int = 5,
    ):
        self.channel = channel
        self.recipient_id = recipient_id
        self.subscription_id = subscription_id
        self.event_type = event_type
        self.message_id = message_id
        self.content = content
        self.metadata = metadata or {}
        self.attempt_number = attempt_number
        self.max_attempts = max_attempts
        
        # Ensure channel is lowercase and valid
        if self.channel not in ("email", "push", "webhook"):
            raise ValueError(f"Invalid delivery channel: {self.channel}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for Celery task args."""
        return {
            "channel": self.channel,
            "recipient_id": self.recipient_id,
            "subscription_id": self.subscription_id,
            "event_type": self.event_type,
            "message_id": self.message_id,
            "content": self.content,
            "metadata": self.metadata,
            "attempt_number": self.attempt_number,
            "max_attempts": self.max_attempts,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeliveryTaskPayload":
        """Deserialize from dictionary after Celery unpacking."""
        return cls(**data)


# ============================================================================
# EXPONENTIAL BACKOFF STRATEGY
# ============================================================================


class ExponentialBackoffStrategy:
    """Exponential backoff calculation for delivery retries.
    
    Formula: delay = base_delay * (backoff_factor ** (attempt - 1))
    
    Example (base=1, factor=2):
      attempt 1: initial delivery (no delay)
      attempt 2: 1 * 2^0 = 1 second
      attempt 3: 1 * 2^1 = 2 seconds
      attempt 4: 1 * 2^2 = 4 seconds
      attempt 5: 1 * 2^3 = 8 seconds
      
    Configurable via settings (WEBHOOK_RETRY_BACKOFF_SECONDS, etc.)
    """
    
    def __init__(
        self,
        base_delay_seconds: int = 1,
        backoff_factor: float = 2.0,
        max_delay_seconds: int = 3600,
    ):
        """Initialize backoff strategy.
        
        Args:
            base_delay_seconds: Initial delay before first retry
            backoff_factor: Multiplier for each retry (typically 2.0)
            max_delay_seconds: Cap on delay to prevent excessive waiting
        """
        self.base_delay_seconds = base_delay_seconds
        self.backoff_factor = backoff_factor
        self.max_delay_seconds = max_delay_seconds
    
    def calculate_delay(self, attempt_number: int) -> int:
        """Calculate delay for given attempt number.
        
        Args:
            attempt_number: Current attempt (1, 2, 3, ...)
            
        Returns:
            Delay in seconds before next retry
        """
        if attempt_number <= 1:
            return 0
        
        # Exponential calculation: base * (factor ^ (attempt - 2))
        # Attempt 2 → 0 * factor^0 = base
        # Attempt 3 → base * factor^1
        delay = self.base_delay_seconds * (self.backoff_factor ** (attempt_number - 2))
        
        # Cap the delay to avoid very long waits
        return min(int(delay), self.max_delay_seconds)
    
    @classmethod
    def from_settings(cls) -> "ExponentialBackoffStrategy":
        """Load strategy configuration from app settings."""
        settings = get_settings()
        # Use webhook settings as default, can be extended per channel
        return cls(
            base_delay_seconds=settings.webhook.retry_backoff_seconds,
            max_delay_seconds=settings.celery.task_time_limit,  # Cap at task time limit
        )


# ============================================================================
# DELIVERY TASK BASE CLASS
# ============================================================================


class DeliveryTaskBase(Task):
    """Base task class for delivery with custom retry/error handling."""
    
    autoretry_for = ()  # Disable automatic retry; we handle it manually
    retry_kwargs = {"max_retries": 0}  # No automatic retries
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log task failure details for monitoring."""
        channel = args[0] if args else "unknown"
        logger.error(
            f"Delivery task failed after all retries",
            extra={
                "task_id": task_id,
                "channel": channel,
                "exception": str(exc),
                "traceback": einfo.traceback,
            },
        )
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Log task retry details."""
        channel = args[0] if args else "unknown"
        logger.warning(
            f"Delivery task retry scheduled",
            extra={
                "task_id": task_id,
                "channel": channel,
                "exception": str(exc),
            },
        )


# ============================================================================
# DELIVERY TASKS
# ============================================================================


@app.task(
    base=DeliveryTaskBase,
    name="send_email_with_retry",
    bind=True,
    queue="email",
)
def send_email_with_retry(self, payload_dict: Dict[str, Any]) -> Dict[str, str]:
    """Send email notification with retry logic on retryable errors.
    
    Task sequence:
      1. Deserialize and validate payload
      2. Attempt delivery via EmailSender adapter
      3. On RetryableEmailError: reschedule with exponential backoff
      4. On NonRetryableEmailError: log failure, mark as failed
      5. Return delivery result
      
    Args:
        payload_dict: Serialized DeliveryTaskPayload dict
        
    Returns:
        Dict with keys:
          - status: "sent" | "failed"
          - attempt: Current attempt number
          - error: Error message if failed
          - timestamp: ISO format delivery timestamp
          
    Raises:
        Will retry on retryable errors until max_attempts exhausted.
    """
    try:
        # Deserialize payload from Celery task args
        payload = DeliveryTaskPayload.from_dict(payload_dict)
        
        logger.info(
            f"Email delivery attempt {payload.attempt_number}/{payload.max_attempts}",
            extra={
                "recipient_id": payload.recipient_id,
                "message_id": payload.message_id,
                "subscription_id": payload.subscription_id,
            },
        )
        
        # TODO: Import and instantiate actual EmailSender adapter
        # For now, this is a template. Real implementation would:
        # sender = EmailSender(settings.email)
        # result = await sender.send_email(...)
        
        # Simulate successful send (will be replaced with real adapter)
        result = {
            "status": "sent",
            "attempt": payload.attempt_number,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        logger.info(f"Email sent successfully", extra={"message_id": payload.message_id})
        return result
        
    except RetryableEmailError as e:
        # Temporary error: retry with exponential backoff
        logger.warning(
            f"Retryable email error: {e.error_code}",
            extra={
                "error": str(e),
                "retry_after": e.retry_after_seconds,
            },
        )
        
        if payload.attempt_number >= payload.max_attempts:
            # Exhausted retries
            logger.error(
                f"Email delivery failed after {payload.max_attempts} attempts",
                extra={"message_id": payload.message_id},
            )
            return {
                "status": "failed",
                "attempt": payload.attempt_number,
                "error": f"Max retries exceeded: {e.error_code}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        
        # Schedule retry with exponential backoff
        backoff = ExponentialBackoffStrategy.from_settings()
        next_attempt = payload.attempt_number + 1
        delay = backoff.calculate_delay(next_attempt)
        
        payload.attempt_number = next_attempt
        self.retry(args=[payload.to_dict()], countdown=delay)
        
    except NonRetryableEmailError as e:
        # Permanent error: don't retry
        logger.error(
            f"Non-retryable email error: {e.error_code}",
            extra={
                "error": str(e),
                "message_id": payload.message_id,
            },
        )
        return {
            "status": "failed",
            "attempt": payload.attempt_number,
            "error": f"Non-retryable error: {e.error_code}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
    except Exception as e:
        # Unknown error: treat as retryable (safe default)
        logger.exception(
            f"Unexpected email error (will retry as unknown)",
            extra={"message_id": payload.message_id},
        )
        
        if payload.attempt_number >= payload.max_attempts:
            logger.error(
                f"Email delivery failed after {payload.max_attempts} attempts (unknown error)",
            )
            return {
                "status": "failed",
                "attempt": payload.attempt_number,
                "error": f"Unknown error: {str(e)}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        
        backoff = ExponentialBackoffStrategy.from_settings()
        next_attempt = payload.attempt_number + 1
        delay = backoff.calculate_delay(next_attempt)
        
        payload.attempt_number = next_attempt
        self.retry(args=[payload.to_dict()], countdown=delay)


@app.task(
    base=DeliveryTaskBase,
    name="send_push_with_retry",
    bind=True,
    queue="push",
)
def send_push_with_retry(self, payload_dict: Dict[str, Any]) -> Dict[str, str]:
    """Send push notification with retry logic on retryable errors.
    
    Same retry strategy as email_with_retry but for push channel.
    See send_email_with_retry for detailed behavior.
    
    Args:
        payload_dict: Serialized DeliveryTaskPayload dict
        
    Returns:
        Dict with status, attempt, optional error, and timestamp
    """
    try:
        payload = DeliveryTaskPayload.from_dict(payload_dict)
        
        logger.info(
            f"Push delivery attempt {payload.attempt_number}/{payload.max_attempts}",
            extra={
                "recipient_id": payload.recipient_id,
                "message_id": payload.message_id,
            },
        )
        
        # TODO: Instantiate PushSender and attempt delivery
        result = {
            "status": "sent",
            "attempt": payload.attempt_number,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        logger.info(f"Push sent successfully", extra={"message_id": payload.message_id})
        return result
        
    except RetryablePushError as e:
        logger.warning(f"Retryable push error: {e.error_code}", extra={"error": str(e)})
        
        if payload.attempt_number >= payload.max_attempts:
            logger.error(
                f"Push delivery failed after {payload.max_attempts} attempts",
                extra={"message_id": payload.message_id},
            )
            return {
                "status": "failed",
                "attempt": payload.attempt_number,
                "error": f"Max retries exceeded: {e.error_code}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        
        backoff = ExponentialBackoffStrategy.from_settings()
        next_attempt = payload.attempt_number + 1
        delay = backoff.calculate_delay(next_attempt)
        
        payload.attempt_number = next_attempt
        self.retry(args=[payload.to_dict()], countdown=delay)
        
    except NonRetryablePushError as e:
        logger.error(f"Non-retryable push error: {e.error_code}", extra={"error": str(e)})
        return {
            "status": "failed",
            "attempt": payload.attempt_number,
            "error": f"Non-retryable error: {e.error_code}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
    except Exception as e:
        logger.exception("Unexpected push error (will retry as unknown)")
        
        if payload.attempt_number >= payload.max_attempts:
            return {
                "status": "failed",
                "attempt": payload.attempt_number,
                "error": f"Unknown error: {str(e)}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        
        backoff = ExponentialBackoffStrategy.from_settings()
        next_attempt = payload.attempt_number + 1
        delay = backoff.calculate_delay(next_attempt)
        
        payload.attempt_number = next_attempt
        self.retry(args=[payload.to_dict()], countdown=delay)


@app.task(
    base=DeliveryTaskBase,
    name="send_webhook_with_retry",
    bind=True,
    queue="webhook",
)
def send_webhook_with_retry(self, payload_dict: Dict[str, Any]) -> Dict[str, str]:
    """Send webhook notification with retry logic on retryable errors.
    
    Same retry strategy as email_with_retry but for webhook channel.
    HTTP error classification:
      - 5xx (500, 502, 503, 504): Retryable server errors
      - 4xx (400, 401, 403, 404, 422): Non-retryable client errors
      - Timeout/Connection: Retryable network issues
      
    See send_email_with_retry for detailed behavior.
    
    Args:
        payload_dict: Serialized DeliveryTaskPayload dict
        
    Returns:
        Dict with status, attempt, optional error, and timestamp
    """
    try:
        payload = DeliveryTaskPayload.from_dict(payload_dict)
        
        logger.info(
            f"Webhook delivery attempt {payload.attempt_number}/{payload.max_attempts}",
            extra={
                "recipient_id": payload.recipient_id,
                "message_id": payload.message_id,
            },
        )
        
        # TODO: Instantiate WebhookSender and attempt delivery
        result = {
            "status": "sent",
            "attempt": payload.attempt_number,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        logger.info(f"Webhook sent successfully", extra={"message_id": payload.message_id})
        return result
        
    except RetryableWebhookError as e:
        logger.warning(
            f"Retryable webhook error: {e.error_code}",
            extra={"http_status": e.http_status, "error": str(e)},
        )
        
        if payload.attempt_number >= payload.max_attempts:
            logger.error(
                f"Webhook delivery failed after {payload.max_attempts} attempts",
                extra={"message_id": payload.message_id},
            )
            return {
                "status": "failed",
                "attempt": payload.attempt_number,
                "error": f"Max retries exceeded: {e.error_code}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        
        backoff = ExponentialBackoffStrategy.from_settings()
        next_attempt = payload.attempt_number + 1
        delay = backoff.calculate_delay(next_attempt)
        
        logger.info(
            f"Scheduling webhook retry",
            extra={
                "next_attempt": next_attempt,
                "delay_seconds": delay,
            },
        )
        
        payload.attempt_number = next_attempt
        self.retry(args=[payload.to_dict()], countdown=delay)
        
    except NonRetryableWebhookError as e:
        logger.error(
            f"Non-retryable webhook error: {e.error_code}",
            extra={"error": str(e)},
        )
        return {
            "status": "failed",
            "attempt": payload.attempt_number,
            "error": f"Non-retryable error: {e.error_code}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
    except Exception as e:
        logger.exception("Unexpected webhook error (will retry as unknown)")
        
        if payload.attempt_number >= payload.max_attempts:
            return {
                "status": "failed",
                "attempt": payload.attempt_number,
                "error": f"Unknown error: {str(e)}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        
        backoff = ExponentialBackoffStrategy.from_settings()
        next_attempt = payload.attempt_number + 1
        delay = backoff.calculate_delay(next_attempt)
        
        payload.attempt_number = next_attempt
        self.retry(args=[payload.to_dict()], countdown=delay)


# ============================================================================
# TASK SUBMISSION HELPER
# ============================================================================


def submit_delivery_task(
    channel: str,
    recipient_id: str,
    subscription_id: str,
    event_type: str,
    message_id: str,
    content: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Submit a delivery task to the appropriate queue.
    
    This helper ensures consistent task submission with proper channel routing
    and payload construction.
    
    Args:
        channel: Delivery channel ("email", "push", or "webhook")
        recipient_id: User ID or endpoint identifier
        subscription_id: Associated subscription ID
        event_type: Weather event type
        message_id: Unique message identifier
        content: Delivery content (title, body, endpoint, etc.)
        metadata: Optional metadata context
        
    Returns:
        Task ID from Celery for tracking delivery status
        
    Raises:
        ValueError: If channel is invalid
        
    Example:
        task_id = submit_delivery_task(
            channel="email",
            recipient_id="user@example.com",
            subscription_id="sub_123",
            event_type="rain",
            message_id="msg_abc",
            content={"subject": "Rain alert", "body": "Rain expected..."},
        )
    """
    settings = get_settings()
    
    # Determine max retries per channel (can be made configurable per channel)
    max_retries = {
        "email": getattr(settings.email, "max_retries", 5),
        "push": getattr(settings.push, "max_retries", 5),
        "webhook": settings.webhook.max_retries,
    }.get(channel, 5)
    
    payload = DeliveryTaskPayload(
        channel=channel,
        recipient_id=recipient_id,
        subscription_id=subscription_id,
        event_type=event_type,
        message_id=message_id,
        content=content,
        metadata=metadata,
        attempt_number=1,
        max_attempts=max_retries,
    )
    
    # Route to appropriate task
    task_name = {
        "email": "send_email_with_retry",
        "push": "send_push_with_retry",
        "webhook": "send_webhook_with_retry",
    }[payload.channel]
    
    result = app.send_task(task_name, args=[payload.to_dict()], queue=channel)
    
    logger.info(
        f"Delivery task submitted to {channel} queue",
        extra={
            "task_id": result.id,
            "message_id": message_id,
            "recipient_id": recipient_id,
        },
    )
    
    return result.id
