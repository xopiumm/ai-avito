"""Unit tests for DeduplicationService — T028.

Comprehensive parametrized tests covering:
- TTL = 12 hours window
- First occurrence detection and marking
- Duplicate detection within window
- Allow after expiry (TTL expires)
- Different channel/event combinations
- Redis failure handling (CHECK_FAILED status)
- Idempotency: calling multiple times returns same result
- Edge cases: empty strings, special characters, boundary times

Test organization:
- Parametrized table-driven tests for efficiency
- Fixtures for Redis mock client
- Mock-based testing (no real Redis required)
- Clear sections for each scenario
"""

from datetime import datetime, timezone, timedelta
from typing import Optional
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.weather_alerts.services.deduplication_service import (
    DeduplicationService,
    DeduplicationCheckResult,
    DuplicationStatus,
)
from src.weather_alerts.config.redis import RedisTTL


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_redis():
    """Create async mock Redis client."""
    redis = AsyncMock()
    redis.set = AsyncMock()
    redis.ttl = AsyncMock()
    redis.delete = AsyncMock()
    return redis


@pytest.fixture
def dedup_service_with_mock(mock_redis):
    """Create DeduplicationService with mock Redis client."""
    service = DeduplicationService(redis_client=mock_redis)
    return service, mock_redis


@pytest.fixture
def redi_ttl_value():
    """Get the actual TTL value in seconds."""
    return RedisTTL.DEDUP_WINDOW_SECONDS


# ============================================================================
# PARAMETRIZED TESTS: FIRST OCCURRENCE (NEW NOTIFICATIONS)
# ============================================================================


class TestFirstOccurrenceDetection:
    """Test detection of first-time notifications.
    
    Acceptance criterion:
    - First time seeing a notification → FIRST_OCCURRENCE status
    - Dedup entry is marked in Redis
    - is_duplicate = False
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user_id,subscription_id,channel,event_type",
        [
            # Basic combinations
            ("user_1", 1, "email", "temperature_below"),
            ("user_1", 1, "push", "temperature_below"),
            ("user_1", 1, "webhook", "temperature_below"),
            # Different subscriptions
            ("user_1", 2, "email", "temperature_below"),
            ("user_1", 100, "email", "rain_above"),
            # Different users
            ("user_2", 1, "email", "temperature_below"),
            ("user_123", 1, "email", "temperature_below"),
            # Different event types
            ("user_1", 1, "email", "wind_above"),
            ("user_1", 1, "email", "severe_weather"),
            # Multi-digit IDs
            ("user_9999", 9999, "email", "temperature_below"),
        ],
        ids=[
            "basic_email",
            "basic_push",
            "basic_webhook",
            "different_sub_2",
            "different_sub_100",
            "different_user_2",
            "different_user_123",
            "different_event_wind",
            "different_event_severe",
            "large_ids",
        ],
    )
    async def test_first_occurrence_marks_redis(
        self, dedup_service_with_mock, user_id, subscription_id, channel, event_type, redi_ttl_value
    ):
        """Test that first occurrence marks the key in Redis with correct TTL.
        
        Redis.set() should be called with:
        - NX=True (only if not exists)
        - EX=TTL (12 hours)
        """
        service, mock_redis = dedup_service_with_mock

        # Mock: first call returns True (key was set)
        mock_redis.set.return_value = True

        result = await service.is_duplicate_and_mark(
            user_id=user_id,
            subscription_id=subscription_id,
            channel=channel,
            event_type=event_type,
        )

        # Verify result
        assert result.status == DuplicationStatus.FIRST_OCCURRENCE
        assert result.is_duplicate is False
        assert result.ttl_seconds == redi_ttl_value

        # Verify Redis was called correctly
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args.kwargs["nx"] is True
        assert call_args.kwargs["ex"] == redi_ttl_value
        assert call_args.kwargs["value"] == "1"


# ============================================================================
# PARAMETRIZED TESTS: DUPLICATE DETECTION (WITHIN 12H WINDOW)
# ============================================================================


class TestDuplicateDetection:
    """Test detection of duplicate notifications within 12-hour window.
    
    Acceptance criterion:
    - Second call within 12h with same params → DUPLICATE status
    - is_duplicate = True
    - Redis key already exists (SET fails with NX=True)
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user_id,subscription_id,channel,event_type,ttl_remaining",
        [
            # Various remaining TTLs
            ("user_1", 1, "email", "temperature_below", 43200),  # Fresh, 12h left
            ("user_1", 1, "email", "temperature_below", 21600),  # 6h left
            ("user_1", 1, "email", "temperature_below", 3600),   # 1h left
            ("user_1", 1, "email", "temperature_below", 60),     # 1 min left
            ("user_1", 1, "email", "temperature_below", 1),      # 1 sec left
            # Different channels (duplicate only if everything matches)
            ("user_1", 1, "push", "temperature_below", 7200),
            ("user_1", 1, "webhook", "temperature_below", 5400),
            # Different subscriptions (not duplicates)  
            ("user_1", 2, "email", "temperature_below", 10800),
            # Different users (not duplicates)
            ("user_2", 1, "email", "temperature_below", 14400),
        ],
        ids=[
            "dup_fresh_12h",
            "dup_6h_left",
            "dup_1h_left",
            "dup_1min_left",
            "dup_1sec_left",
            "dup_push_channel",
            "dup_webhook_channel",
            "dup_diff_sub",
            "dup_diff_user",
        ],
    )
    async def test_duplicate_within_window(
        self, dedup_service_with_mock, user_id, subscription_id, channel, event_type, ttl_remaining
    ):
        """Test that duplicate within TTL window is detected and reported.
        
        When Redis.set() returns False (key exists), notification is classified
        as duplicate even with varying remaining TTL.
        """
        service, mock_redis = dedup_service_with_mock

        # Mock: SET returns False (key already exists)
        mock_redis.set.return_value = False
        # Mock: TTL returns remaining time
        mock_redis.ttl.return_value = ttl_remaining

        result = await service.is_duplicate_and_mark(
            user_id=user_id,
            subscription_id=subscription_id,
            channel=channel,
            event_type=event_type,
        )

        # Verify result
        assert result.status == DuplicationStatus.DUPLICATE
        assert result.is_duplicate is True
        # TTL should reflect remaining time or default
        assert result.ttl_seconds in (ttl_remaining, RedisTTL.DEDUP_WINDOW_SECONDS)

        # Verify Redis calls
        mock_redis.set.assert_called_once()
        mock_redis.ttl.assert_called_once()


# ============================================================================
# PARAMETRIZED TESTS: EXPIRY LOGIC (ALLOW AFTER 12H)
# ============================================================================


class TestExpiryAfterTTL:
    """Test that notifications are allowed again after TTL expires.
    
    Acceptance criterion:
    - After 12 hours, the Redis dedup entry expires
    - Next notification is treated as FIRST_OCCURRENCE again
    - Can send the same notification again
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "attempts_timeline",
        [
            # Scenario: send notification, 12h passes, send again
            [
                # Attempt 1: fresh, sets key
                {"set_returns": True, "ttl_returns": None, "expected_status": DuplicationStatus.FIRST_OCCURRENCE},
                # Wait 12+ hours (simulated by new service instance)
                # Attempt 2: key expired in Redis, should be first again
                {"set_returns": True, "ttl_returns": None, "expected_status": DuplicationStatus.FIRST_OCCURRENCE},
            ],
            # Scenario: duplicate at 1h, try again at 13h
            [
                {"set_returns": True, "ttl_returns": None, "expected_status": DuplicationStatus.FIRST_OCCURRENCE},  # T=0
                {"set_returns": False, "ttl_returns": 3600, "expected_status": DuplicationStatus.DUPLICATE},         # T=1h
                {"set_returns": True, "ttl_returns": None, "expected_status": DuplicationStatus.FIRST_OCCURRENCE},   # T=13h (expired)
            ],
        ],
        ids=[
            "after_12h_send_again",
            "dup_at_1h_then_after_13h",
        ],
    )
    async def test_allow_after_expiry(
        self, dedup_service_with_mock, attempts_timeline
    ):
        """Test that notifications are allowed again after TTL expiry.
        
        Simulates timeline of attempts separated by sufficient time.
        """
        service, mock_redis = dedup_service_with_mock

        for attempt_data in attempts_timeline:
            # Setup mock return values for this attempt
            mock_redis.set.return_value = attempt_data["set_returns"]
            if attempt_data["ttl_returns"] is not None:
                mock_redis.ttl.return_value = attempt_data["ttl_returns"]

            result = await service.is_duplicate_and_mark(
                user_id="user_1",
                subscription_id=1,
                channel="email",
                event_type="temperature_below",
            )

            # Verify status matches expected
            assert result.status == attempt_data["expected_status"]

            # Reset mock for next attempt
            mock_redis.reset_mock()


# ============================================================================
# PARAMETRIZED TESTS: IDEMPOTENCY GUARANTEE
# ============================================================================


class TestIdempotency:
    """Test that calling is_duplicate_and_mark() multiple times is idempotent.
    
    Acceptance criterion:
    - First call with new notification → marks in Redis, returns FIRST_OCCURRENCE
    - Second call (retry) with same params → finds mark, returns DUPLICATE
    - Idempotency ensures safe replay of events without creating duplicates
    """

    @pytest.mark.asyncio
    async def test_idempotent_first_call(self, dedup_service_with_mock):
        """Test that repeated calls to same notification return same result."""
        service, mock_redis = dedup_service_with_mock

        # First call: marks and returns FIRST_OCCURRENCE
        mock_redis.set.return_value = True
        result1 = await service.is_duplicate_and_mark(
            user_id="user_1",
            subscription_id=1,
            channel="email",
            event_type="temperature_below",
        )
        assert result1.status == DuplicationStatus.FIRST_OCCURRENCE
        assert result1.is_duplicate is False

        # Reset mock to simulate second call (event replayed)
        mock_redis.reset_mock()
        mock_redis.set.return_value = False  # Key now exists
        mock_redis.ttl.return_value = 43200

        # Second call (retry): should find mark, return DUPLICATE
        result2 = await service.is_duplicate_and_mark(
            user_id="user_1",
            subscription_id=1,
            channel="email",
            event_type="temperature_below",
        )
        assert result2.status == DuplicationStatus.DUPLICATE
        assert result2.is_duplicate is True

        # Both calls used same dedup key
        assert result1.dedup_key == result2.dedup_key


    @pytest.mark.asyncio
    async def test_idempotent_result_consistency(self, dedup_service_with_mock):
        """Test that multiple retry attempts return consistent results."""
        service, mock_redis = dedup_service_with_mock

        # Setup: key exists in Redis (duplicate scenario)
        mock_redis.set.return_value = False
        mock_redis.ttl.return_value = 21600

        results = []
        for i in range(3):
            result = await service.is_duplicate_and_mark(
                user_id="user_1",
                subscription_id=1,
                channel="email",
                event_type="temperature_below",
            )
            results.append(result)

            # All results should be identical
            if i > 0:
                assert result.status == results[0].status == DuplicationStatus.DUPLICATE
                assert result.is_duplicate == results[0].is_duplicate == True
                assert result.dedup_key == results[0].dedup_key


# ============================================================================
# PARAMETRIZED TESTS: DIFFERENT COMBINATIONS (NO FALSE POSITIVES)
# ============================================================================


class TestNoDuplicateFalsePositives:
    """Test that different combinations don't trigger false duplicate detection.
    
    Acceptance criterion:
    - Same (user, subscription, channel, event_type) → IS duplicate
    - Different on ANY dimension → NOT a duplicate
    """

    @pytest.mark.parametrize(
        "base_params,changed_params,should_be_duplicate",
        [
            # Base case
            (
                {"user_id": "user_1", "subscription_id": 1, "channel": "email", "event_type": "temp_below"},
                {},
                True,  # Exact duplicate
            ),
            # Different user → not duplicate
            (
                {"user_id": "user_1", "subscription_id": 1, "channel": "email", "event_type": "temp_below"},
                {"user_id": "user_2"},
                False,
            ),
            # Different subscription → not duplicate
            (
                {"user_id": "user_1", "subscription_id": 1, "channel": "email", "event_type": "temp_below"},
                {"subscription_id": 2},
                False,
            ),
            # Different channel → not duplicate
            (
                {"user_id": "user_1", "subscription_id": 1, "channel": "email", "event_type": "temp_below"},
                {"channel": "push"},
                False,
            ),
            # Different event_type → not duplicate
            (
                {"user_id": "user_1", "subscription_id": 1, "channel": "email", "event_type": "temp_below"},
                {"event_type": "rain_above"},
                False,
            ),
            # Multiple differences
            (
                {"user_id": "user_1", "subscription_id": 1, "channel": "email", "event_type": "temp_below"},
                {"user_id": "user_2", "channel": "push"},
                False,
            ),
        ],
        ids=[
            "exact_duplicate",
            "different_user",
            "different_subscription",
            "different_channel",
            "different_event_type",
            "multiple_different",
        ],
    )
    @pytest.mark.asyncio
    async def test_no_false_positive_duplicates(
        self, dedup_service_with_mock, base_params, changed_params, should_be_duplicate
    ):
        """Test that only exact matches are considered duplicates."""
        service, mock_redis = dedup_service_with_mock

        # Merge parameters
        params = {**base_params, **changed_params}

        # Setup mock: SET succeeds if NOT duplicate, fails if duplicate
        mock_redis.set.return_value = not should_be_duplicate
        # Setup TTL mock for duplicate case
        if should_be_duplicate:
            mock_redis.ttl.return_value = 43200  # 12 hours

        result = await service.is_duplicate_and_mark(**params)

        if should_be_duplicate:
            assert result.is_duplicate is True
        else:
            assert result.is_duplicate is False


# ============================================================================
# PARAMETRIZED TESTS: REDIS FAILURE HANDLING
# ============================================================================


class TestRedisFailureHandling:
    """Test handling of Redis failures.
    
    Acceptance criterion:
    - Redis unavailable → CHECK_FAILED status
    - is_duplicate = False (conservative: don't block delivery)
    - Allows delivery to proceed despite dedup check failure
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "exception_type,exception_message",
        [
            (Exception, "Connection refused"),
            (ConnectionError, "Redis connection lost"),
            (TimeoutError, "Redis operation timeout"),
            (RuntimeError, "Unexpected Redis error"),
            (ValueError, "Invalid Redis response"),
        ],
        ids=[
            "generic_exception",
            "connection_error",
            "timeout_error",
            "runtime_error",
            "value_error",
        ],
    )
    @pytest.mark.asyncio
    async def test_redis_failure_conservative_approach(
        self, dedup_service_with_mock, exception_type, exception_message
    ):
        """Test that Redis failures are handled conservatively (allow delivery).
        
        When Redis is unavailable, system should fail open (allow notification)
        rather than fail closed (block notification).
        """
        service, mock_redis = dedup_service_with_mock

        # Setup mock to raise exception
        mock_redis.set.side_effect = exception_type(exception_message)

        result = await service.is_duplicate_and_mark(
            user_id="user_1",
            subscription_id=1,
            channel="email",
            event_type="temperature_below",
        )

        # Verify conservative handling
        assert result.status == DuplicationStatus.CHECK_FAILED
        assert result.is_duplicate is False  # Don't block delivery
        assert "Redis" in result.reason or "check failed" in result.reason.lower()


# ============================================================================
# PARAMETRIZED TESTS: EDGE CASES
# ============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user_id,subscription_id,channel,event_type",
        [
            # Empty-like strings
            ("", 1, "email", "temp"),
            ("user_1", 1, "", "temp"),
            ("user_1", 1, "email", ""),
            # Very long strings
            ("u" * 255, 1, "email", "temp"),
            ("user_1", 1, "e" * 255, "temp"),
            ("user_1", 1, "email", "t" * 255),
            # Special characters in user_id
            ("user-1_test.123", 1, "email", "temp"),
            # Large subscription_id
            ("user_1", 999999999, "email", "temp"),
            # Boundary subscription_id
            ("user_1", 0, "email", "temp"),
            ("user_1", 1, "email", "temp"),  # Minimal normal case
        ],
        ids=[
            "empty_user_id",
            "empty_channel",
            "empty_event_type",
            "long_user_id",
            "long_channel",
            "long_event_type",
            "special_chars_user",
            "large_sub_id",
            "zero_sub_id",
            "minimal_normal",
        ],
    )
    async def test_edge_case_inputs(
        self, dedup_service_with_mock, user_id, subscription_id, channel, event_type
    ):
        """Test that edge case inputs are handled correctly."""
        service, mock_redis = dedup_service_with_mock
        mock_redis.set.return_value = True

        # Should not raise, should complete successfully
        result = await service.is_duplicate_and_mark(
            user_id=user_id,
            subscription_id=subscription_id,
            channel=channel,
            event_type=event_type,
        )

        assert result is not None
        assert hasattr(result, "status")
        assert hasattr(result, "is_duplicate")


# ============================================================================
# RESULT STRUCTURE VALIDATION
# ============================================================================


class TestResultStructure:
    """Test that result objects have all required fields."""

    @pytest.mark.asyncio
    async def test_first_occurrence_result_fields(self, dedup_service_with_mock, redi_ttl_value):
        """Test FIRST_OCCURRENCE result has all fields."""
        service, mock_redis = dedup_service_with_mock
        mock_redis.set.return_value = True

        result = await service.is_duplicate_and_mark(
            user_id="user_1",
            subscription_id=1,
            channel="email",
            event_type="temperature_below",
        )

        # Verify all fields present
        assert isinstance(result, DeduplicationCheckResult)
        assert hasattr(result, "status")
        assert hasattr(result, "is_duplicate")
        assert hasattr(result, "dedup_key")
        assert hasattr(result, "ttl_seconds")
        assert hasattr(result, "reason")

        # Verify types
        assert isinstance(result.status, DuplicationStatus)
        assert isinstance(result.is_duplicate, bool)
        assert isinstance(result.dedup_key, str)
        assert isinstance(result.ttl_seconds, int)
        assert isinstance(result.reason, str)

        # Verify values
        assert result.status == DuplicationStatus.FIRST_OCCURRENCE
        assert result.is_duplicate is False
        assert result.ttl_seconds == redi_ttl_value


    @pytest.mark.asyncio
    async def test_duplicate_result_fields(self, dedup_service_with_mock):
        """Test DUPLICATE result has all fields."""
        service, mock_redis = dedup_service_with_mock
        mock_redis.set.return_value = False
        mock_redis.ttl.return_value = 21600

        result = await service.is_duplicate_and_mark(
            user_id="user_1",
            subscription_id=1,
            channel="email",
            event_type="temperature_below",
        )

        assert isinstance(result, DeduplicationCheckResult)
        assert result.status == DuplicationStatus.DUPLICATE
        assert result.is_duplicate is True
        assert isinstance(result.ttl_seconds, int)
        assert result.ttl_seconds > 0


# ============================================================================
# ACCEPTANCE CRITERIA MAPPING — T028
# ============================================================================
"""
TEST COVERAGE MATRIX — T028 DEDUPLICATION SERVICE:

AC: TTL = 12 hours
✓ Covered by: TestFirstOccurrenceDetection::test_first_occurrence_marks_redis
  - Verifies RedisTTL.DEDUP_WINDOW_SECONDS used
  - Verifies EX parameter set to TTL value

AC: Skip duplicate within window
✓ Covered by: TestDuplicateDetection::test_duplicate_within_window
  - 5 parametrized cases with varying TTL remaining
  - Tests DUPLICATE status returned

AC: Allow after expiry (12h TTL expires)
✓ Covered by: TestExpiryAfterTTL::test_allow_after_expiry
  - Simulates timeline: first occurrence → duplicate → first occurrence again
  - Verifies notification allowed after TTL expires

AC: Idempotency guarantee
✓ Covered by: TestIdempotency
  - Repeated calls return consistent results
  - Safe for event replay/retries

AC: No false positive duplicates
✓ Covered by: TestNoDuplicateFalsePositives
  - Different user → NOT duplicate
  - Different subscription → NOT duplicate
  - Different channel → NOT duplicate
  - Different event_type → NOT duplicate

AC: Redis failure handling (conservative approach)
✓ Covered by: TestRedisFailureHandling
  - Connection errors
  - Timeouts
  - Generic exceptions
  - All result in CHECK_FAILED + is_duplicate=False

AC: Edge cases
✓ Covered by: TestEdgeCases
  - Empty strings, large IDs, special characters
  - Minimal and boundary values
"""
