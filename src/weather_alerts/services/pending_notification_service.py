"""PendingNotificationService for Weather Alerts (T022).

Manages pending notifications that are waiting for delivery schedules to open.

Business logic:
- When a weather event is detected but delivery window is closed, notification goes to pending
- When window opens, pending notifications are released for delivery
- If subscription is deleted/disabled, pending notifications are cancelled
- Pending state is stored in Redis (no persistence needed currently)

Integration points:
1. Orchestrator creates pending → calls create_pending()
2. Scheduling system wakes up at window open → calls release_pending()
3. Subscription service deletes/disables → calls cancel_pending_for_subscription()

State transitions:
- Created: Notification created, waiting for window to open
- Released: Window opened, notification ready for sending
- Cancelled: Subscription deleted/disabled, discard notification
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum as PyEnum
from typing import Optional, List
import json

from redis.asyncio import Redis

from src.weather_alerts.config.redis import (
    get_redis_client,
    RedisKeyBuilder,
    RedisTTL,
)
from src.weather_alerts.services.condition_evaluation_service import EventType


# ============================================================================
# RESULT MODELS - TESTABLE INTERFACES
# ============================================================================


class PendingStatus(str, PyEnum):
    """Status of a pending notification."""
    
    # Successfully stored in pending, waiting for window to open
    STORED = "stored"
    
    # Window opened, notification released for delivery
    RELEASED = "released"
    
    # Subscription deleted/disabled, cancelled without delivery
    CANCELLED = "cancelled"
    
    # Storage or release failed
    OPERATION_FAILED = "operation_failed"


@dataclass
class PendingNotificationState:
    """Represents a pending notification in storage.
    
    Attributes:
        pending_id: Unique identifier (generated from user, sub, event)
        user_id: User who owns the subscription
        subscription_id: Which subscription
        location_id: Which location
        event_type: Type of weather event (for templating on release)
        matched_conditions_count: How many conditions matched
        window_opens_at_utc: When delivery window opens (from schedule service)
        window_closes_at_utc: When delivery window closes
        source_forecast_timestamp: When forecast was from (for display/audit)
        created_at_utc: When this pending was created
        expires_at_utc: When pending automatically expires (7 days)
        channels: List of active delivery channels at time of creation (for release)
    """
    
    pending_id: str
    user_id: str
    subscription_id: int
    location_id: int
    event_type: EventType
    matched_conditions_count: int
    window_opens_at_utc: datetime
    window_closes_at_utc: datetime
    source_forecast_timestamp: datetime
    created_at_utc: datetime
    expires_at_utc: datetime
    channels: List[dict] = field(default_factory=list)  # [{id, type, destination}, ...]
    
    def to_json(self) -> str:
        """Serialize to JSON for Redis storage."""
        return json.dumps({
            "pending_id": self.pending_id,
            "user_id": self.user_id,
            "subscription_id": self.subscription_id,
            "location_id": self.location_id,
            "event_type": str(self.event_type),
            "matched_conditions_count": self.matched_conditions_count,
            "window_opens_at_utc": self.window_opens_at_utc.isoformat(),
            "window_closes_at_utc": self.window_closes_at_utc.isoformat(),
            "source_forecast_timestamp": self.source_forecast_timestamp.isoformat(),
            "created_at_utc": self.created_at_utc.isoformat(),
            "expires_at_utc": self.expires_at_utc.isoformat(),
            "channels": self.channels,
        })
    
    @classmethod
    def from_json(cls, json_str: str) -> "PendingNotificationState":
        """Deserialize from JSON."""
        data = json.loads(json_str)
        return cls(
            pending_id=data["pending_id"],
            user_id=data["user_id"],
            subscription_id=data["subscription_id"],
            location_id=data["location_id"],
            event_type=EventType(data["event_type"]),
            matched_conditions_count=data["matched_conditions_count"],
            window_opens_at_utc=datetime.fromisoformat(data["window_opens_at_utc"]),
            window_closes_at_utc=datetime.fromisoformat(data["window_closes_at_utc"]),
            source_forecast_timestamp=datetime.fromisoformat(data["source_forecast_timestamp"]),
            created_at_utc=datetime.fromisoformat(data["created_at_utc"]),
            expires_at_utc=datetime.fromisoformat(data["expires_at_utc"]),
            channels=data.get("channels", []),
        )


@dataclass
class PendingOperationResult:
    """Result of a pending operation (create, release, cancel).
    
    Attributes:
        status: PendingStatus - was operation successful?
        pending_state: The pending notification state (if successful)
        reason: Human-readable explanation (for logs)
        operation_time_ms: How long operation took (for monitoring)
    """
    
    status: PendingStatus
    pending_state: Optional[PendingNotificationState] = None
    reason: str = ""
    operation_time_ms: int = 0


# ============================================================================
# PENDING NOTIFICATION SERVICE
# ============================================================================


class PendingNotificationService:
    """Service for managing pending notifications (T022).
    
    Responsibilities:
    1. Create: Store pending notification when window is closed
    2. Release: Retrieve and mark as released when window opens
    3. Cancel: Delete pending when subscription is deleted/disabled
    
    Storage:
    - Pending notifications stored in Redis (no DB persistence)
    - Key: pending:{user_id}:{subscription_id}:{unique_event_id}
    - Value: JSON-serialized PendingNotificationState
    - TTL: 7 days (RedisTTL.PENDING_NOTIFICATION_SECONDS)
    
    Integration:
    - Orchestrator calls create_pending() for notifications with closed window
    - Scheduler calls release_pending() when window opens
    - SubscriptionService calls cancel_pending_for_subscription() on delete/disable
    """
    
    def __init__(self, redis_client: Optional[Redis] = None):
        """Initialize service with Redis client.
        
        Args:
            redis_client: Redis async client. If None, will be obtained from get_redis_client()
        """
        self.redis = redis_client

    async def _get_redis(self) -> Redis:
        """Get Redis client (lazy initialization).
        
        Returns:
            Redis: Async Redis client
        """
        if self.redis is None:
            self.redis = await get_redis_client()
        return self.redis

    def _generate_pending_id(
        self,
        user_id: str,
        subscription_id: int,
        event_type: str,
        created_at_utc: datetime,
    ) -> str:
        """Generate unique pending ID.
        
        Format: {user_id}_{subscription_id}_{event_type}_{timestamp_ms}
        
        Ensures uniqueness even if multiple events for same subscription/type
        are created at nearly the same time.
        
        Args:
            user_id: User identifier
            subscription_id: Subscription ID
            event_type: Type of event
            created_at_utc: Timestamp of creation
            
        Returns:
            str: Unique pending ID
        """
        timestamp_ms = int(created_at_utc.timestamp() * 1000)
        return f"{user_id}_{subscription_id}_{event_type}_{timestamp_ms}"

    async def create_pending(
        self,
        user_id: str,
        subscription_id: int,
        location_id: int,
        event_type: EventType,
        matched_conditions_count: int,
        window_opens_at_utc: datetime,
        window_closes_at_utc: datetime,
        source_forecast_timestamp: datetime,
        channels: List[dict],  # [{id, type, destination}, ...]
    ) -> PendingOperationResult:
        """Create a pending notification for later delivery.
        
        Called by orchestrator when:
        - Conditions match
        - Schedule window is CLOSED
        - Need to wait for window to open
        
        Args:
            user_id: User ID
            subscription_id: Subscription ID
            location_id: Location ID
            event_type: Event type from condition evaluation
            matched_conditions_count: How many conditions matched
            window_opens_at_utc: When window opens (from schedule service)
            window_closes_at_utc: When window closes
            source_forecast_timestamp: Forecast timestamp
            channels: Active delivery channels (snapshot at creation time)
        
        Returns:
            PendingOperationResult with status and details
            
        Example:
            result = await service.create_pending(
                user_id="user_123",
                subscription_id=42,
                location_id=1,
                event_type=EventType.TEMPERATURE_ALERT,
                matched_conditions_count=1,
                window_opens_at_utc=datetime(...),
                window_closes_at_utc=datetime(...),
                source_forecast_timestamp=datetime(...),
                channels=[
                    {"id": 1, "type": "email", "destination": "user@example.com"},
                    {"id": 2, "type": "push", "destination": "device_token_123"},
                ]
            )
            
            if result.status == PendingStatus.STORED:
                print(f"Pending created, will release at {result.pending_state.window_opens_at_utc}")
        """
        start_time = datetime.now(timezone.utc)
        
        try:
            created_at_utc = datetime.now(timezone.utc)
            expires_at_utc = created_at_utc + timedelta(seconds=RedisTTL.PENDING_NOTIFICATION_SECONDS)
            
            # Generate unique pending ID
            pending_id = self._generate_pending_id(
                user_id=user_id,
                subscription_id=subscription_id,
                event_type=str(event_type),
                created_at_utc=created_at_utc,
            )
            
            # Create pending state
            pending_state = PendingNotificationState(
                pending_id=pending_id,
                user_id=user_id,
                subscription_id=subscription_id,
                location_id=location_id,
                event_type=event_type,
                matched_conditions_count=matched_conditions_count,
                window_opens_at_utc=window_opens_at_utc,
                window_closes_at_utc=window_closes_at_utc,
                source_forecast_timestamp=source_forecast_timestamp,
                created_at_utc=created_at_utc,
                expires_at_utc=expires_at_utc,
                channels=channels,
            )
            
            # Build Redis key using pending_notification_key pattern
            # This pattern allows querying by subscription for bulk operations
            redis_key = RedisKeyBuilder.pending_notification_key(
                user_id=user_id,
                subscription_id=subscription_id,
                event_id=pending_id,
            )
            
            # Store in Redis with TTL
            redis = await self._get_redis()
            await redis.set(
                name=redis_key,
                value=pending_state.to_json(),
                ex=RedisTTL.PENDING_NOTIFICATION_SECONDS,  # 7 days
            )
            
            end_time = datetime.now(timezone.utc)
            operation_time_ms = int((end_time - start_time).total_seconds() * 1000)
            
            return PendingOperationResult(
                status=PendingStatus.STORED,
                pending_state=pending_state,
                reason=f"Pending created, releases at {window_opens_at_utc.isoformat()}",
                operation_time_ms=operation_time_ms,
            )
            
        except Exception as e:
            end_time = datetime.now(timezone.utc)
            operation_time_ms = int((end_time - start_time).total_seconds() * 1000)
            
            return PendingOperationResult(
                status=PendingStatus.OPERATION_FAILED,
                reason=f"Failed to create pending: {str(e)}",
                operation_time_ms=operation_time_ms,
            )

    async def release_pending(
        self,
        user_id: str,
        subscription_id: int,
    ) -> List[PendingOperationResult]:
        """Release all pending notifications for a subscription.
        
        Called by scheduler when:
        - Delivery window opens
        - Need to check if pending notifications should be sent
        
        Returns the pending notifications to be delivered (if still valid).
        
        Args:
            user_id: User ID
            subscription_id: Subscription ID
            
        Returns:
            List of PendingOperationResult with RELEASED status for each pending found
            
        Example:
            results = await service.release_pending(
                user_id="user_123",
                subscription_id=42,
            )
            
            for result in results:
                if result.status == PendingStatus.RELEASED:
                    pending = result.pending_state
                    # Prepare notifications for delivery
                    for channel in pending.channels:
                        await delivery_service.send(pending, channel)
        """
        start_time = datetime.now(timezone.utc)
        results = []
        
        try:
            redis = await self._get_redis()
            
            # Build pattern to find all pending for this subscription
            pattern = RedisKeyBuilder.pending_by_subscription_key(subscription_id)
            
            # Scan all matching keys (non-blocking, handles large datasets)
            cursor = 0
            while True:
                cursor, keys = await redis.scan(
                    cursor=cursor,
                    match=f"pending:{user_id}:{subscription_id}:*",
                    count=100,
                )
                
                if keys:
                    # Get all pending notifications
                    for key in keys:
                        try:
                            pending_json = await redis.get(key)
                            if pending_json:
                                pending_state = PendingNotificationState.from_json(pending_json)
                                
                                # Mark as released (technically just return it for processing)
                                result = PendingOperationResult(
                                    status=PendingStatus.RELEASED,
                                    pending_state=pending_state,
                                    reason=f"Released for delivery at {start_time.isoformat()}",
                                )
                                results.append(result)
                                
                                # Delete the pending entry (it's now being processed)
                                await redis.delete(key)
                        except Exception as e:
                            # Log error but continue with others
                            results.append(PendingOperationResult(
                                status=PendingStatus.OPERATION_FAILED,
                                reason=f"Failed to release pending: {str(e)}",
                            ))
                
                if cursor == 0:
                    break
            
            return results
            
        except Exception as e:
            return [PendingOperationResult(
                status=PendingStatus.OPERATION_FAILED,
                reason=f"Failed to release pending notifications: {str(e)}",
            )]

    async def cancel_pending_for_subscription(
        self,
        subscription_id: int,
    ) -> int:
        """Cancel all pending notifications for a subscription.
        
        Called by subscription service when:
        - Subscription is DELETED
        - Subscription is DISABLED
        
        Cancels all waiting pending notifications for this subscription.
        
        Args:
            subscription_id: Subscription ID to cancel all pending for
            
        Returns:
            int: Number of pending notifications cancelled
            
        Example:
            count = await service.cancel_pending_for_subscription(42)
            print(f"Cancelled {count} pending notifications")
        """
        try:
            redis = await self._get_redis()
            
            # Build pattern for all pending for this subscription
            pattern = RedisKeyBuilder.pending_by_subscription_key(subscription_id)
            
            deleted_count = 0
            cursor = 0
            
            # Use SCAN to iterate (non-blocking)
            while True:
                cursor, keys = await redis.scan(
                    cursor=cursor,
                    match=f"pending:*:{subscription_id}:*",
                    count=100,
                )
                
                if keys:
                    await redis.delete(*keys)
                    deleted_count += len(keys)
                
                if cursor == 0:
                    break
            
            return deleted_count
            
        except Exception:
            # Error during cleanup, don't fail the subscription delete
            return 0

    async def cancel_pending(
        self,
        user_id: str,
        subscription_id: int,
        pending_id: str,
    ) -> bool:
        """Cancel a specific pending notification.
        
        Args:
            user_id: User ID
            subscription_id: Subscription ID
            pending_id: Pending notification ID
            
        Returns:
            bool: True if deleted, False if didn't exist or error
        """
        try:
            redis = await self._get_redis()
            key = RedisKeyBuilder.pending_notification_key(
                user_id=user_id,
                subscription_id=subscription_id,
                event_id=pending_id,
            )
            result = await redis.delete(key)
            return result > 0
        except Exception:
            return False

    async def get_pending(
        self,
        user_id: str,
        subscription_id: int,
        pending_id: str,
    ) -> Optional[PendingNotificationState]:
        """Retrieve a specific pending notification.
        
        Args:
            user_id: User ID
            subscription_id: Subscription ID
            pending_id: Pending notification ID
            
        Returns:
            PendingNotificationState if found, None otherwise
        """
        try:
            redis = await self._get_redis()
            key = RedisKeyBuilder.pending_notification_key(
                user_id=user_id,
                subscription_id=subscription_id,
                event_id=pending_id,
            )
            pending_json = await redis.get(key)
            if pending_json:
                return PendingNotificationState.from_json(pending_json)
            return None
        except Exception:
            return None

    async def list_pending_for_subscription(
        self,
        subscription_id: int,
    ) -> List[PendingNotificationState]:
        """List all pending notifications for a subscription.
        
        Useful for admin/debugging purposes.
        
        Args:
            subscription_id: Subscription ID
            
        Returns:
            List of pending notifications
        """
        try:
            redis = await self._get_redis()
            
            pending_list = []
            cursor = 0
            
            while True:
                cursor, keys = await redis.scan(
                    cursor=cursor,
                    match=f"pending:*:{subscription_id}:*",
                    count=100,
                )
                
                if keys:
                    for key in keys:
                        pending_json = await redis.get(key)
                        if pending_json:
                            pending_list.append(PendingNotificationState.from_json(pending_json))
                
                if cursor == 0:
                    break
            
            return pending_list
            
        except Exception:
            return []
