"""Redis client and key management utilities for Weather Alerts service.

Redis is used for:
1. Deduplication: store delivered (user, subscription, channel, event_type) tuples with 12h TTL
2. Pending notifications: store pending delivery tasks when schedule window is closed
3. Celery coordination: broker and result backend via CELERY_BROKER_URL and CELERY_RESULT_BACKEND
"""

from typing import Optional

import redis.asyncio as aioredis
from redis.asyncio import Redis

from src.weather_alerts.config.settings import get_settings


# Global Redis client instance
_redis_client: Optional[Redis] = None


async def get_redis_client() -> Redis:
    """Get or create Redis async client.
    
    Lazy initialization: client created on first access and reused thereafter.
    Connection parameters loaded from settings (REDIS_URL).
    
    Returns:
        Redis: Async Redis client connected to REDIS_URL
        
    Raises:
        ConnectionError: If unable to connect to Redis
        
    Example:
        redis = await get_redis_client()
        await redis.set("key", "value", ex=3600)
    """
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        # Parse REDIS_URL and create async client
        _redis_client = await aioredis.from_url(
            settings.redis.url,
            encoding="utf-8",
            decode_responses=True,  # Return strings instead of bytes
            socket_timeout=settings.redis.socket_timeout,
            socket_connect_timeout=settings.redis.socket_timeout,
            socket_keepalive=True,
            health_check_interval=30,  # Check connection health every 30s
        )
    return _redis_client


async def close_redis() -> None:
    """Close Redis connection.
    
    Call this during application shutdown to properly dispose of resources.
    
    Example:
        # In FastAPI lifespan
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # startup
            yield
            # shutdown
            await close_redis()
    """
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


async def ping_redis() -> bool:
    """Test Redis connectivity.
    
    Returns:
        bool: True if Redis is accessible, False otherwise
    """
    try:
        redis = await get_redis_client()
        result = await redis.ping()
        return result is True
    except Exception:
        return False


# ============================================================================
# KEY BUILDERS - Centralized key generation for Redis
# ============================================================================
# Key naming convention: {namespace}:{category}:{identifiers}
# This ensures clarity and helps with monitoring/debugging


class RedisKeyBuilder:
    """Unified builder for Redis keys across all services."""

    # Namespaces
    NAMESPACE_DEDUP = "dedup"
    NAMESPACE_PENDING = "pending"
    NAMESPACE_RETRY = "retry"
    NAMESPACE_CELERY = "celery"

    @staticmethod
    def dedup_key(
        user_id: str,
        subscription_id: int,
        channel: str,
        event_type: str,
    ) -> str:
        """Build deduplication key.
        
        Format: dedup:{user_id}:{subscription_id}:{channel}:{event_type}
        
        Used to prevent duplicate notifications for the same:
        - user
        - subscription
        - delivery channel (email, push, webhook)
        - weather event type (e.g., rain_probability_above)
        
        TTL: 12 hours (per spec requirement)
        
        Args:
            user_id: External user identifier
            subscription_id: Internal subscription ID
            channel: Delivery channel (email, push, webhook)
            event_type: Weather condition type (temperature_below, rain_probability_above, etc.)
            
        Returns:
            str: Redis key for dedup tracking
            
        Example:
            key = RedisKeyBuilder.dedup_key("user123", 42, "email", "temperature_below")
            # Returns: "dedup:user123:42:email:temperature_below"
        """
        return f"{RedisKeyBuilder.NAMESPACE_DEDUP}:{user_id}:{subscription_id}:{channel}:{event_type}"

    @staticmethod
    def pending_notification_key(
        user_id: str,
        subscription_id: int,
        event_id: str,
    ) -> str:
        """Build pending notification key.
        
        Format: pending:{user_id}:{subscription_id}:{event_id}
        
        Used to track notifications waiting for:
        - Schedule window to open (e.g., user set delivery window 08:00-20:00, but event occurred at 21:00)
        - Manual retry after failure
        
        The value stored can be serialized event data (JSON) for quick reprocessing.
        
        Args:
            user_id: External user identifier
            subscription_id: Internal subscription ID
            event_id: Unique weather event identifier
            
        Returns:
            str: Redis key for pending notification tracking
            
        Example:
            key = RedisKeyBuilder.pending_notification_key("user123", 42, "event_20260409_001")
            # Returns: "pending:user123:42:event_20260409_001"
        """
        return f"{RedisKeyBuilder.NAMESPACE_PENDING}:{user_id}:{subscription_id}:{event_id}"

    @staticmethod
    def pending_by_subscription_key(
        subscription_id: int,
    ) -> str:
        """Build pattern key for all pending notifications by subscription.
        
        Format: pending:*:{subscription_id}:*
        
        Used to scan/clean pending notifications for a specific subscription
        (e.g., when subscription is deleted).
        
        Args:
            subscription_id: Internal subscription ID
            
        Returns:
            str: Redis key pattern for subscription pending notifications
            
        Example:
            pattern = RedisKeyBuilder.pending_by_subscription_key(42)
            # Returns: "pending:*:42:*"
            # Can be used with redis.scan_iter(match=pattern)
        """
        return f"{RedisKeyBuilder.NAMESPACE_PENDING}:*:{subscription_id}:*"

    @staticmethod
    def retry_metadata_key(
        task_id: str,
    ) -> str:
        """Build retry metadata key for failed delivery attempts.
        
        Format: retry:{task_id}
        
        Stores metadata about retry attempts:
        - attempt count
        - last error
        - next retry time
        - backoff multiplier state
        
        Primarily used when retry state is stored in Redis (complementary to Celery task tracking).
        
        Args:
            task_id: Unique task identifier (from Celery or custom)
            
        Returns:
            str: Redis key for retry metadata
            
        Example:
            key = RedisKeyBuilder.retry_metadata_key("task_abc123def456")
            # Returns: "retry:task_abc123def456"
        """
        return f"{RedisKeyBuilder.NAMESPACE_RETRY}:{task_id}"

    @staticmethod
    def health_check_key() -> str:
        """Build health check key for monitoring Redis connectivity.
        
        Format: health:ping
        
        Used to verify Redis is operational.
        
        Returns:
            str: Redis key for health check
        """
        return f"health:ping"


# ============================================================================
# TTL CONSTANTS
# ============================================================================

class RedisTTL:
    """Predefined TTL values for Redis operations."""

    # Deduplication window: 12 hours as per spec requirement
    # After 12 hours, same event can trigger notification again
    DEDUP_WINDOW_SECONDS = 12 * 60 * 60  # 43200

    # Pending notification: 7 days
    # Enough time to retry failing deliveries
    PENDING_NOTIFICATION_SECONDS = 7 * 24 * 60 * 60  # 604800

    # Retry metadata: 24 hours
    # Track retry attempts for a day
    RETRY_METADATA_SECONDS = 24 * 60 * 60  # 86400

    # Temporary operations: 5 minutes
    # For short-lived coordination
    TEMPORARY_SECONDS = 5 * 60  # 300


# ============================================================================
# EXAMPLE USAGE (for reference)
# ============================================================================

"""
# In services/deduplication_service.py:
from src.weather_alerts.config.redis import (
    get_redis_client,
    RedisKeyBuilder,
    RedisTTL,
)

async def check_and_mark_duplicate(
    user_id: str,
    subscription_id: int,
    channel: str,
    event_type: str,
) -> bool:
    \"\"\"Check if notification already sent (dedup).
    
    Returns:
        bool: True if duplicate (should skip), False if allowed
    \"\"\"
    redis = get_redis_client()
    key = RedisKeyBuilder.dedup_key(user_id, subscription_id, channel, event_type)
    
    # Check if key exists (means we already sent this notification)
    exists = await redis.exists(key)
    
    if not exists:
        # Mark as sent with 12-hour TTL
        await redis.setex(key, RedisTTL.DEDUP_WINDOW_SECONDS, "1")
        return False  # Not a duplicate, proceed with delivery
    
    return True  # Duplicate, skip


# In services/pending_notification_service.py:
async def store_pending_notification(
    user_id: str,
    subscription_id: int,
    event_id: str,
    notification_data: dict,
) -> None:
    \"\"\"Store pending notification for later delivery.\"\"\"
    redis = get_redis_client()
    key = RedisKeyBuilder.pending_notification_key(user_id, subscription_id, event_id)
    
    import json
    await redis.setex(
        key,
        RedisTTL.PENDING_NOTIFICATION_SECONDS,
        json.dumps(notification_data),
    )


async def get_pending_notifications_for_subscription(
    subscription_id: int,
) -> list:
    \"\"\"Get all pending notifications for a subscription.\"\"\"
    redis = get_redis_client()
    pattern = RedisKeyBuilder.pending_by_subscription_key(subscription_id)
    
    pending = []
    async for key in redis.scan_iter(match=pattern):
        data = await redis.get(key)
        if data:
            import json
            pending.append(json.loads(data))
    
    return pending


async def clean_pending_for_subscription(subscription_id: int) -> int:
    \"\"\"Remove all pending notifications for deleted subscription.\"\"\"
    redis = get_redis_client()
    pattern = RedisKeyBuilder.pending_by_subscription_key(subscription_id)
    
    keys = []
    async for key in redis.scan_iter(match=pattern):
        keys.append(key)
    
    if keys:
        return await redis.delete(*keys)
    
    return 0
"""
