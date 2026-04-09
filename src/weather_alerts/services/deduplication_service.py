"""DeduplicationService for Weather Alerts (T020).

This service prevents duplicate notifications within a 12-hour window using Redis.

Business logic:
- Duplicate is defined as: same (user, subscription, channel, event_type) within 12 hours
- After 12 hours, if condition becomes true again, new notification is allowed
- Uses Redis TTL to automatically expire dedup entries

Technical approach:
- Uses Redis SET command with NX (only if not exists) and EX (expire) options
- This provides atomic check-and-set semantics without explicit locks
- Atomicity ensures that even with concurrent requests, only one notification is sent

Idempotency considerations:
- Service is idempotent: calling is_duplicate_and_mark() multiple times for the same
  notification returns the same result (first call marks, subsequent calls find the mark)
- This means retry/reprocessing of events won't create duplicate notifications
- If orchestrator processes the same event twice, second invocation will detect
  the mark from first invocation and skip the notification

Integration points:
- Called from notification_orchestrator.py after condition evaluation and schedule check
- Takes the prepared notification and checks/marks deduplication before sending
- If is_duplicate_and_mark() returns True, notification should be skipped
"""

from dataclasses import dataclass
from enum import Enum as PyEnum
from typing import Optional

from redis.asyncio import Redis

from src.weather_alerts.config.redis import (
    get_redis_client,
    RedisKeyBuilder,
    RedisTTL,
)


# ============================================================================
# RESULT MODELS - TESTABLE INTERFACES
# ============================================================================


class DuplicationStatus(str, PyEnum):
    """Result of deduplication check."""
    
    # This is the first notification for this combination in the window
    # Safe to send, and dedup entry has been marked in Redis
    FIRST_OCCURRENCE = "first_occurrence"
    
    # Already saw this notification within the 12-hour window
    # Should skip delivery to prevent duplicate
    DUPLICATE = "duplicate"
    
    # Redis unavailable or check failed
    # Conservative approach: assume not duplicate and allow delivery
    CHECK_FAILED = "check_failed"


@dataclass
class DeduplicationCheckResult:
    """Result of checking and marking deduplication.
    
    Attributes:
        status: DuplicationStatus - is this a duplicate?
        is_duplicate: Convenience boolean (status == DUPLICATE)
        dedup_key: Redis key used for this check (useful for debugging)
        ttl_seconds: TTL of the dedup entry in Redis
        reason: Human-readable explanation (for logs)
        
    Examples:
        First time seeing a notification:
        >>> result.status == DuplicationStatus.FIRST_OCCURRENCE
        >>> result.is_duplicate == False
        
        Second time within 12 hours:
        >>> result.status == DuplicationStatus.DUPLICATE
        >>> result.is_duplicate == True
        
        After 12 hours, Redis entry expires automatically:
        >>> result.status == DuplicationStatus.FIRST_OCCURRENCE  # Can send again
    """
    
    status: DuplicationStatus
    is_duplicate: bool
    dedup_key: str
    ttl_seconds: int
    reason: str


# ============================================================================
# DEDUPLICATION SERVICE
# ============================================================================


class DeduplicationService:
    """Service for preventing duplicate notifications using Redis TTL.
    
    Thread-safe and idempotent: concurrent requests are handled correctly,
    and retrying the same operation produces the same result.
    
    Atomic algorithm (via Redis SET with NX and EX):
    1. Try to SET key with NX (only if not exists) and EX (expire in 12h)
    2. If SET succeeds, this is the first occurrence -> allow notification
    3. If SET fails, the key already exists -> duplicate, skip notification
    4. After 12 hours, Redis automatically expires the key
    
    This avoids race conditions without explicit locks.
    """

    def __init__(self, redis_client: Optional[Redis] = None):
        """Initialize service with Redis client.
        
        Args:
            redis_client: Redis async client. If None, will be obtained from get_redis_client()
        """
        self.redis = redis_client

    async def _get_redis(self) -> Redis:
        """Get Redis client (lazy initialization on first use).
        
        Returns:
            Redis: Async Redis client
        """
        if self.redis is None:
            self.redis = await get_redis_client()
        return self.redis

    async def is_duplicate_and_mark(
        self,
        user_id: str,
        subscription_id: int,
        channel: str,
        event_type: str,
    ) -> DeduplicationCheckResult:
        """Check if notification is duplicate and mark it in Redis.
        
        This method implements the core deduplication logic with atomic check-and-set.
        
        Args:
            user_id: External user identifier
            subscription_id: Internal subscription ID
            channel: Delivery channel (email, push, webhook)
            event_type: Weather condition type (temperature_below, rain_probability_above, etc.)
            
        Returns:
            DeduplicationCheckResult with status and details
            
        Raises:
            None - Always returns a result, even if Redis check fails (conservative approach)
            
        Pure logic (no side effects if you check but don't mark via separate method):
        Use this method when you want to mark immediately. If you want to check first
        and mark later, use is_duplicate() and mark_as_delivered() separately.
        
        IDEMPOTENCY GUARANTEE:
        =====================
        Calling this method multiple times with the same parameters within 12 hours
        returns the same result (after first call, subsequent calls will see
        the mark and return DUPLICATE status).
        
        This is critical for handling event retries:
        - First processing: FIRST_OCCURRENCE (mark is set)
        - Event replayed due to retry: DUPLICATE (mark from first attempt found)
        - After 12h expiry: FIRST_OCCURRENCE again (original mark expired)
        
        Example 1 - Happy path (first notification):
        >>> result = await service.is_duplicate_and_mark(
        ...     user_id="user_123",
        ...     subscription_id=42,
        ...     channel="email",
        ...     event_type="temperature_below"
        ... )
        >>> result.status == DuplicationStatus.FIRST_OCCURRENCE
        >>> result.is_duplicate is False
        
        Example 2 - Duplicate within window:
        >>> # Send same notification again (within 12h)
        >>> result = await service.is_duplicate_and_mark(
        ...     user_id="user_123",
        ...     subscription_id=42,
        ...     channel="email",
        ...     event_type="temperature_below"
        ... )
        >>> result.status == DuplicationStatus.DUPLICATE
        >>> result.is_duplicate is True
        >>> result.reason contains "already notified"
        
        Example 3 - Different channel (not a duplicate):
        >>> # Same user/subscription, but different channel (push vs email)
        >>> result = await service.is_duplicate_and_mark(
        ...     user_id="user_123",
        ...     subscription_id=42,
        ...     channel="push",  # Different channel
        ...     event_type="temperature_below"
        ... )
        >>> result.status == DuplicationStatus.FIRST_OCCURRENCE  # Not a duplicate
        >>> result.is_duplicate is False
        
        Integration example (from orchestrator):
        >>> # After condition evaluation and schedule check pass
        >>> dedup_result = await service.is_duplicate_and_mark(
        ...     user_id=prepared_notification.user_id,
        ...     subscription_id=prepared_notification.subscription_id,
        ...     channel=prepared_notification.delivery_channel_type,
        ...     event_type=str(prepared_notification.event_type)
        ... )
        
        >>> if dedup_result.is_duplicate:
        ...     # Skip sending, log as deduplicated
        ...     logger.info(f"Skipping duplicate: {dedup_result.reason}")
        ...     return
        >>> else:
        ...     # First occurrence, proceed with sending
        ...     await delivery_service.send(prepared_notification)
        """
        try:
            redis = await self._get_redis()
            dedup_key = RedisKeyBuilder.dedup_key(
                user_id=user_id,
                subscription_id=subscription_id,
                channel=channel,
                event_type=event_type,
            )
            
            # Atomic check-and-set operation with TTL
            # SET key ex=TTL nx=True means:
            # - SET the key with value "1" (marker)
            # - Only if the key does NOT exist (nx=True)
            # - With expiration time of TTL seconds (ex=TTL)
            # Returns True if key was SET (first occurrence)
            # Returns False if key already existed (duplicate)
            
            was_set = await redis.set(
                name=dedup_key,
                value="1",  # Marker value (content doesn't matter, just presence)
                ex=RedisTTL.DEDUP_WINDOW_SECONDS,  # 12 hours
                nx=True,  # Only set if not exists
            )
            
            if was_set:
                # First occurrence: successfully set the mark
                return DeduplicationCheckResult(
                    status=DuplicationStatus.FIRST_OCCURRENCE,
                    is_duplicate=False,
                    dedup_key=dedup_key,
                    ttl_seconds=RedisTTL.DEDUP_WINDOW_SECONDS,
                    reason=f"First notification for {user_id}/{subscription_id}/{channel}/{event_type}",
                )
            else:
                # Duplicate: key already exists
                # Get TTL to provide more context
                ttl = await redis.ttl(dedup_key)
                return DeduplicationCheckResult(
                    status=DuplicationStatus.DUPLICATE,
                    is_duplicate=True,
                    dedup_key=dedup_key,
                    ttl_seconds=ttl if ttl >= 0 else RedisTTL.DEDUP_WINDOW_SECONDS,
                    reason=f"Already notified {user_id}/{subscription_id}/{channel}/{event_type} within 12h",
                )
                
        except Exception as e:
            # Redis check failed (connection issue, etc.)
            # Conservative approach: don't block delivery
            # Log the error and return CHECK_FAILED status
            # Caller should decide whether to allow delivery anyway
            dedup_key = RedisKeyBuilder.dedup_key(
                user_id=user_id,
                subscription_id=subscription_id,
                channel=channel,
                event_type=event_type,
            )
            return DeduplicationCheckResult(
                status=DuplicationStatus.CHECK_FAILED,
                is_duplicate=False,  # Don't skip if check fails
                dedup_key=dedup_key,
                ttl_seconds=RedisTTL.DEDUP_WINDOW_SECONDS,
                reason=f"Dedup check failed: {str(e)}. Allowing delivery.",
            )

    async def is_duplicate(
        self,
        user_id: str,
        subscription_id: int,
        channel: str,
        event_type: str,
    ) -> bool:
        """Check if notification would be duplicate WITHOUT marking.
        
        Use this when you want to check first and mark later separately.
        This is useful for pre-filtering before expensive operations.
        
        Args:
            user_id: External user identifier
            subscription_id: Internal subscription ID
            channel: Delivery channel (email, push, webhook)
            event_type: Weather condition type
            
        Returns:
            bool: True if duplicate, False if first occurrence or check failed
        """
        try:
            redis = await self._get_redis()
            dedup_key = RedisKeyBuilder.dedup_key(
                user_id=user_id,
                subscription_id=subscription_id,
                channel=channel,
                event_type=event_type,
            )
            exists = await redis.exists(dedup_key)
            return exists > 0
        except Exception:
            # Check failed, assume not duplicate (conservative)
            return False

    async def mark_as_delivered(
        self,
        user_id: str,
        subscription_id: int,
        channel: str,
        event_type: str,
    ) -> bool:
        """Mark notification as delivered in dedup window.
        
        Use this when you checked with is_duplicate() and want to mark separately.
        
        Args:
            user_id: External user identifier
            subscription_id: Internal subscription ID
            channel: Delivery channel
            event_type: Weather condition type
            
        Returns:
            bool: True if mark was set, False if already existed
        """
        try:
            redis = await self._get_redis()
            dedup_key = RedisKeyBuilder.dedup_key(
                user_id=user_id,
                subscription_id=subscription_id,
                channel=channel,
                event_type=event_type,
            )
            was_set = await redis.set(
                name=dedup_key,
                value="1",
                ex=RedisTTL.DEDUP_WINDOW_SECONDS,
                nx=True,
            )
            return was_set
        except Exception:
            # Mark failed but don't raise (delivery is more important)
            return False

    async def clear_dedup_mark(
        self,
        user_id: str,
        subscription_id: int,
        channel: str,
        event_type: str,
    ) -> bool:
        """Manually clear dedup mark (for testing or admin operations).
        
        Useful for clearing marks before 12h expiry for testing or manual admin ops.
        
        Args:
            user_id: External user identifier
            subscription_id: Internal subscription ID
            channel: Delivery channel
            event_type: Weather condition type
            
        Returns:
            bool: True if key was deleted, False if didn't exist
        """
        try:
            redis = await self._get_redis()
            dedup_key = RedisKeyBuilder.dedup_key(
                user_id=user_id,
                subscription_id=subscription_id,
                channel=channel,
                event_type=event_type,
            )
            result = await redis.delete(dedup_key)
            return result > 0
        except Exception:
            return False

    async def clear_subscription_dedup(
        self,
        subscription_id: int,
    ) -> int:
        """Clear all dedup marks for a subscription (useful when deleting subscription).
        
        Scans all dedup keys for this subscription and deletes them.
        
        Args:
            subscription_id: Internal subscription ID
            
        Returns:
            int: Number of dedup entries deleted
        """
        try:
            redis = await self._get_redis()
            pattern = f"{RedisKeyBuilder.NAMESPACE_DEDUP}:*:{subscription_id}:*:*"
            
            deleted_count = 0
            cursor = 0
            
            # Use SCAN to iterate (non-blocking for large datasets)
            while True:
                cursor, keys = await redis.scan(
                    cursor=cursor,
                    match=pattern,
                    count=100,
                )
                
                if keys:
                    await redis.delete(*keys)
                    deleted_count += len(keys)
                
                if cursor == 0:
                    break
            
            return deleted_count
        except Exception:
            return 0
