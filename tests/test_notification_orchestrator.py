"""Unit tests for NotificationOrchestrator.

Tests cover:
- Main orchestration workflow
- Condition evaluation integration
- Schedule checking integration
- Preparing notifications for immediate delivery
- Preparing pending notification requests
- Filtering subscriptions and channels
- Metrics collection
- Error handling
"""

from datetime import datetime, timezone, time, date
from typing import List, Optional

import pytest

from src.weather_alerts.adapters.weather_provider import (
    CurrentWeather,
    DailyForecast,
    Forecast,
)
from src.weather_alerts.domain.models.subscription import (
    Subscription,
    SubscriptionStatus,
    SubscriptionCondition,
    DeliveryChannel,
    DeliveryChannelType,
    ConditionType,
)
from src.weather_alerts.services.condition_evaluation_service import (
    ConditionEvaluationService,
    EventType,
)
from src.weather_alerts.services.schedule_service import ScheduleService
from src.weather_alerts.services.notification_orchestrator import (
    NotificationOrchestrator,
    NotificationState,
    OrchestrationResult,
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def orchestrator():
    """Create an orchestrator with real services."""
    return NotificationOrchestrator(
        condition_service=ConditionEvaluationService(),
        schedule_service=ScheduleService(),
    )


class MockLocation:
    """Mock Location."""
    
    def __init__(self, location_id: int = 1, timezone_str: str = "UTC"):
        self.id = location_id
        self.timezone = timezone_str


@pytest.fixture
def utc_location():
    """UTC location (no timezone complexity)."""
    return MockLocation(location_id=1, timezone_str="UTC")


@pytest.fixture
def forecast_normal():
    """Standard forecast for testing."""
    current = CurrentWeather(
        location_id=1,
        timestamp=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
        temperature_celsius=15.0,
        feels_like_celsius=14.0,
        wind_speed_kmh=10.0,
        rain_probability=30.0,
        rain_amount_mm=0.5,
        description="Partly cloudy",
        severe_event=None,
    )
    tomorrow = DailyForecast(
        location_id=1,
        forecast_date=date(2026, 4, 10),
        temp_min_celsius=10.0,
        temp_max_celsius=20.0,
        temp_avg_celsius=15.0,
        rain_probability=40.0,
        rain_amount_mm=1.0,
        wind_speed_kmh=12.0,
        description="Scattered showers",
        severe_event=None,
    )
    return Forecast(location_id=1, current=current, tomorrow=tomorrow)


def create_mock_subscription(
    subscription_id: int = 1,
    user_id: str = "user1",
    location: Optional[MockLocation] = None,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
    active_from: Optional[str] = None,
    active_to: Optional[str] = None,
    conditions: Optional[List[SubscriptionCondition]] = None,
    channels: Optional[List[DeliveryChannel]] = None,
) -> Subscription:
    """Helper to create mock subscription."""
    if location is None:
        location = MockLocation()
    
    subscription = Subscription(
        id=subscription_id,
        user_id=user_id,
        location_id=location.id,
        status=status,
        condition_mode="ANY",
        schedule_timezone_source="location",
        active_from=active_from,
        active_to=active_to,
    )
    subscription.location = location
    
    # Add conditions if provided
    if conditions:
        subscription.conditions = conditions
    else:
        # Default: temperature_below 20°C
        cond = SubscriptionCondition(
            id=1,
            subscription_id=subscription_id,
            type=ConditionType.TEMPERATURE_BELOW,
            threshold_value=20.0,
            threshold_unit="°C",
        )
        subscription.conditions = [cond]
    
    # Add channels if provided
    if channels:
        subscription.channels = channels
    else:
        # Default: one email channel
        ch = DeliveryChannel(
            id=1,
            subscription_id=subscription_id,
            type=DeliveryChannelType.EMAIL,
            destination="user@example.com",
            active=True,
        )
        subscription.channels = [ch]
    
    return subscription


# ============================================================================
# MAIN WORKFLOW TESTS
# ============================================================================


def test_orchestration_matching_and_allowed(
    orchestrator,
    forecast_normal,
    utc_location,
):
    """Test full workflow: conditions match and window is open."""
    subscription = create_mock_subscription(
        location=utc_location,
        active_from=None,  # No window restrictions
        active_to=None,
    )
    
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast_normal,
        evaluation_time_utc=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
    )
    
    assert len(result.prepared_notifications) == 1
    assert len(result.pending_requests) == 0
    assert result.metrics.subscriptions_matched == 1
    assert result.metrics.subscriptions_allowed == 1


def test_orchestration_matching_but_blocked(
    orchestrator,
    forecast_normal,
    utc_location,
):
    """Test full workflow: conditions match but window is closed."""
    subscription = create_mock_subscription(
        location=utc_location,
        active_from="08:00",
        active_to="12:00",  # Closed at 12:00
    )
    
    # Check at 13:00 UTC (window is closed, next opens tomorrow at 08:00)
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast_normal,
        evaluation_time_utc=datetime(2026, 4, 9, 13, 0, 0, tzinfo=timezone.utc),
    )
    
    assert len(result.prepared_notifications) == 0
    assert len(result.pending_requests) == 1  # Goes to pending
    assert result.metrics.subscriptions_matched == 1
    assert result.metrics.subscriptions_allowed == 0
    assert result.metrics.subscriptions_pending == 1


def test_orchestration_conditions_not_matched(
    orchestrator,
    forecast_normal,
    utc_location,
):
    """Test workflow: conditions don't match."""
    # Create condition: temperature > 25°C (actual is 15°C)
    cond = SubscriptionCondition(
        id=1,
        subscription_id=1,
        type=ConditionType.TEMPERATURE_ABOVE,
        threshold_value=25.0,
        threshold_unit="°C",
    )
    subscription = create_mock_subscription(
        location=utc_location,
        conditions=[cond],
    )
    
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast_normal,
        evaluation_time_utc=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
    )
    
    assert len(result.prepared_notifications) == 0
    assert len(result.pending_requests) == 0
    assert result.metrics.subscriptions_matched == 0
    assert result.metrics.subscriptions_skipped == 1


# ============================================================================
# SUBSCRIPTION STATUS FILTERING
# ============================================================================


def test_skip_disabled_subscription(
    orchestrator,
    forecast_normal,
    utc_location,
):
    """Test that DISABLED subscriptions are skipped."""
    subscription = create_mock_subscription(
        location=utc_location,
        status=SubscriptionStatus.DISABLED,
    )
    
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast_normal,
    )
    
    assert result.metrics.subscriptions_evaluated == 0
    assert result.metrics.subscriptions_skipped == 0


def test_skip_deleted_subscription(
    orchestrator,
    forecast_normal,
    utc_location,
):
    """Test that DELETED subscriptions are skipped."""
    subscription = create_mock_subscription(
        location=utc_location,
        status=SubscriptionStatus.DELETED,
    )
    
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast_normal,
    )
    
    assert result.metrics.subscriptions_evaluated == 0


def test_only_process_active_subscriptions(
    orchestrator,
    forecast_normal,
    utc_location,
):
    """Test that only ACTIVE subscriptions are processed."""
    active_sub = create_mock_subscription(
        subscription_id=1,
        location=utc_location,
        status=SubscriptionStatus.ACTIVE,
    )
    disabled_sub = create_mock_subscription(
        subscription_id=2,
        location=utc_location,
        status=SubscriptionStatus.DISABLED,
    )
    
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[active_sub, disabled_sub],
        forecast=forecast_normal,
    )
    
    assert result.metrics.subscriptions_evaluated == 1  # Only active


# ============================================================================
# DELIVERY CHANNEL TESTS
# ============================================================================


def test_multiple_channels_create_multiple_notifications(
    orchestrator,
    forecast_normal,
    utc_location,
):
    """Test that multiple active channels create multiple notifications."""
    channels = [
        DeliveryChannel(
            id=1,
            subscription_id=1,
            type=DeliveryChannelType.EMAIL,
            destination="user@example.com",
            active=True,
        ),
        DeliveryChannel(
            id=2,
            subscription_id=1,
            type=DeliveryChannelType.PUSH,
            destination="device_token_123",
            active=True,
        ),
        DeliveryChannel(
            id=3,
            subscription_id=1,
            type=DeliveryChannelType.WEBHOOK,
            destination="https://example.com/webhook",
            active=True,
        ),
    ]
    
    subscription = create_mock_subscription(
        location=utc_location,
        channels=channels,
    )
    
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast_normal,
    )
    
    assert len(result.prepared_notifications) == 3
    assert result.prepared_notifications[0].delivery_channel_type == DeliveryChannelType.EMAIL
    assert result.prepared_notifications[1].delivery_channel_type == DeliveryChannelType.PUSH
    assert result.prepared_notifications[2].delivery_channel_type == DeliveryChannelType.WEBHOOK


def test_skip_inactive_channels(
    orchestrator,
    forecast_normal,
    utc_location,
):
    """Test that inactive channels are skipped."""
    channels = [
        DeliveryChannel(
            id=1,
            subscription_id=1,
            type=DeliveryChannelType.EMAIL,
            destination="user@example.com",
            active=True,
        ),
        DeliveryChannel(
            id=2,
            subscription_id=1,
            type=DeliveryChannelType.PUSH,
            destination="device_token_123",
            active=False,  # Inactive
        ),
    ]
    
    subscription = create_mock_subscription(
        location=utc_location,
        channels=channels,
    )
    
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast_normal,
    )
    
    assert len(result.prepared_notifications) == 1  # Only active channel
    assert result.prepared_notifications[0].delivery_channel_type == DeliveryChannelType.EMAIL


def test_no_notifications_if_no_active_channels(
    orchestrator,
    forecast_normal,
    utc_location,
):
    """Test that no notifications are prepared if all channels are inactive."""
    channels = [
        DeliveryChannel(
            id=1,
            subscription_id=1,
            type=DeliveryChannelType.EMAIL,
            destination="user@example.com",
            active=False,
        ),
    ]
    
    subscription = create_mock_subscription(
        location=utc_location,
        channels=channels,
    )
    
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast_normal,
    )
    
    assert len(result.prepared_notifications) == 0


# ============================================================================
# PREPARED NOTIFICATION STRUCTURE TESTS
# ============================================================================


def test_prepared_notification_contains_all_fields(
    orchestrator,
    forecast_normal,
    utc_location,
):
    """Test that prepared notifications have all required fields."""
    subscription = create_mock_subscription(location=utc_location)
    
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast_normal,
    )
    
    notification = result.prepared_notifications[0]
    assert notification.subscription_id == subscription.id
    assert notification.user_id == subscription.user_id
    assert notification.location_id == subscription.location_id
    assert notification.delivery_channel_id is not None
    assert notification.delivery_channel_type is not None
    assert notification.destination is not None
    assert notification.event_type is not None
    assert notification.matched_conditions_count > 0
    assert notification.send_at_utc is not None
    assert notification.source_forecast_timestamp is not None


def test_prepared_notification_send_time_is_now(
    orchestrator,
    forecast_normal,
    utc_location,
):
    """Test that prepared notifications have send_at_utc = evaluation time."""
    eval_time = datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)
    subscription = create_mock_subscription(location=utc_location)
    
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast_normal,
        evaluation_time_utc=eval_time,
    )
    
    notification = result.prepared_notifications[0]
    assert notification.send_at_utc == eval_time


# ============================================================================
# PENDING NOTIFICATION REQUEST TESTS
# ============================================================================


def test_pending_request_contains_all_fields(
    orchestrator,
    forecast_normal,
    utc_location,
):
    """Test that pending requests have all required fields."""
    subscription = create_mock_subscription(
        location=utc_location,
        active_from="08:00",
        active_to="12:00",
    )
    
    # Check at 13:00 (window closed)
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast_normal,
        evaluation_time_utc=datetime(2026, 4, 9, 13, 0, 0, tzinfo=timezone.utc),
    )
    
    pending = result.pending_requests[0]
    assert pending.subscription_id == subscription.id
    assert pending.location_id == subscription.location_id
    assert pending.event_type is not None
    assert pending.matched_conditions_count > 0
    assert pending.window_opens_at_utc is not None
    assert pending.source_forecast_timestamp is not None


def test_pending_request_next_window_tomorrow_after_hours(
    orchestrator,
    forecast_normal,
    utc_location,
):
    """Test that pending request next window is tomorrow if after hours."""
    subscription = create_mock_subscription(
        location=utc_location,
        active_from="08:00",
        active_to="12:00",
    )
    
    # Check at 13:00 (window closed, will open tomorrow at 08:00)
    eval_time = datetime(2026, 4, 9, 13, 0, 0, tzinfo=timezone.utc)
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast_normal,
        evaluation_time_utc=eval_time,
    )
    
    pending = result.pending_requests[0]
    # Next window should be tomorrow at 08:00 UTC
    expected_next_open = datetime(2026, 4, 10, 8, 0, 0, tzinfo=timezone.utc)
    assert pending.window_opens_at_utc == expected_next_open


# ============================================================================
# METRICS TESTS
# ============================================================================


def test_metrics_all_matched_and_allowed(
    orchestrator,
    forecast_normal,
    utc_location,
):
    """Test metrics when all conditions are matched and allowed."""
    subs = [
        create_mock_subscription(subscription_id=i, location=utc_location)
        for i in range(1, 4)  # 3 subscriptions
    ]
    
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=subs,
        forecast=forecast_normal,
    )
    
    assert result.metrics.subscriptions_evaluated == 3
    assert result.metrics.subscriptions_matched == 3
    assert result.metrics.subscriptions_allowed == 3
    assert result.metrics.subscriptions_pending == 0
    assert result.metrics.subscriptions_skipped == 0
    assert result.metrics.total_notifications_prepared == 3  # 1 channel each


def test_metrics_mixed_scenarios(
    orchestrator,
    forecast_normal,
    utc_location,
):
    """Test metrics with mixed scenarios (matched, skipped, pending)."""
    # Active and matches
    sub1 = create_mock_subscription(subscription_id=1, location=utc_location)
    
    # Active but doesn't match (temp > 25)
    cond2 = SubscriptionCondition(
        id=1,
        subscription_id=2,
        type=ConditionType.TEMPERATURE_ABOVE,
        threshold_value=25.0,
        threshold_unit="°C",
    )
    sub2 = create_mock_subscription(
        subscription_id=2,
        location=utc_location,
        conditions=[cond2],
    )
    
    # Active, matches, but window closed
    sub3 = create_mock_subscription(
        subscription_id=3,
        location=utc_location,
        active_from="08:00",
        active_to="12:00",  # Closed at 12:00
    )
    
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[sub1, sub2, sub3],
        forecast=forecast_normal,
        evaluation_time_utc=datetime(2026, 4, 9, 13, 0, 0, tzinfo=timezone.utc),
    )
    
    assert result.metrics.subscriptions_evaluated == 3
    assert result.metrics.subscriptions_matched == 2  # sub1, sub3
    assert result.metrics.subscriptions_allowed == 1  # sub1
    assert result.metrics.subscriptions_pending == 1  # sub3
    assert result.metrics.subscriptions_skipped == 1  # sub2


def test_metrics_execution_time_is_set(
    orchestrator,
    forecast_normal,
    utc_location,
):
    """Test that execution time is measured."""
    subscription = create_mock_subscription(location=utc_location)
    
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast_normal,
    )
    
    assert result.execution_time_ms >= 0  # Should be non-negative


# ============================================================================
# MULTIPLE SUBSCRIPTIONS TESTS
# ============================================================================


def test_multiple_subscriptions_independent_evaluation(
    orchestrator,
    forecast_normal,
    utc_location,
):
    """Test that multiple subscriptions are evaluated independently."""
    # Sub1: temp < 20 (matches: 15 < 20)
    cond1 = SubscriptionCondition(
        id=1,
        subscription_id=1,
        type=ConditionType.TEMPERATURE_BELOW,
        threshold_value=20.0,
        threshold_unit="°C",
    )
    sub1 = create_mock_subscription(
        subscription_id=1,
        location=utc_location,
        conditions=[cond1],
    )
    
    # Sub2: temp > 20 (doesn't match: 15 < 20)
    cond2 = SubscriptionCondition(
        id=2,
        subscription_id=2,
        type=ConditionType.TEMPERATURE_ABOVE,
        threshold_value=20.0,
        threshold_unit="°C",
    )
    sub2 = create_mock_subscription(
        subscription_id=2,
        location=utc_location,
        conditions=[cond2],
    )
    
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[sub1, sub2],
        forecast=forecast_normal,
    )
    
    assert result.metrics.subscriptions_matched == 1  # Only sub1
    assert result.metrics.subscriptions_skipped == 1  # sub2
    assert len(result.prepared_notifications) == 1  # Only from sub1
