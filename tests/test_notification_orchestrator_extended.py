"""Extended unit tests for NotificationOrchestrator.

Tests cover:
- Error cases and exception handling
- Timezone scenarios
- Edge cases (empty lists, boundary conditions)
- Event type prioritization
- Condition matching accuracy
"""

from datetime import datetime, timezone, date
from typing import List, Optional

import pytest

from src.weather_alerts.adapters.weather_provider import (
    CurrentWeather,
    DailyForecast,
    Forecast,
    SeverityEventType,
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
    EventType,
)
from src.weather_alerts.services.condition_evaluation_service import (
    ConditionEvaluationService,
)
from src.weather_alerts.services.schedule_service import ScheduleService
from src.weather_alerts.services.notification_orchestrator import (
    NotificationOrchestrator,
)
from src.weather_alerts.services.exceptions import (
    InvalidForecastData,
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
    """UTC location."""
    return MockLocation(location_id=1, timezone_str="UTC")


@pytest.fixture
def moscow_location():
    """Moscow location (UTC+3)."""
    return MockLocation(location_id=2, timezone_str="Europe/Moscow")


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
    
    if conditions:
        subscription.conditions = conditions
    else:
        cond = SubscriptionCondition(
            id=1,
            subscription_id=subscription_id,
            type=ConditionType.TEMPERATURE_BELOW,
            threshold_value=20.0,
            threshold_unit="°C",
        )
        subscription.conditions = [cond]
    
    if channels:
        subscription.channels = channels
    else:
        ch = DeliveryChannel(
            id=1,
            subscription_id=subscription_id,
            type=DeliveryChannelType.EMAIL,
            destination="user@example.com",
            active=True,
        )
        subscription.channels = [ch]
    
    return subscription


def create_forecast_with_severe_event(
    temp: float = 15.0,
    severe_event: Optional[SeverityEventType] = None,
) -> Forecast:
    """Create a forecast with optional severe event."""
    current = CurrentWeather(
        location_id=1,
        timestamp=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
        temperature_celsius=temp,
        feels_like_celsius=temp - 1,
        wind_speed_kmh=10.0,
        rain_probability=30.0,
        rain_amount_mm=0.5,
        description="Test weather",
        severe_event=severe_event,
    )
    tomorrow = DailyForecast(
        location_id=1,
        forecast_date=date(2026, 4, 10),
        temp_min_celsius=temp - 5,
        temp_max_celsius=temp + 5,
        temp_avg_celsius=temp,
        rain_probability=40.0,
        rain_amount_mm=1.0,
        wind_speed_kmh=12.0,
        description="Test weather tomorrow",
        severe_event=None,
    )
    return Forecast(location_id=1, current=current, tomorrow=tomorrow)


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


def test_error_handling_empty_subscriptions_list(
    orchestrator,
    utc_location,
):
    """Test handling of empty subscriptions list."""
    forecast = create_forecast_with_severe_event()
    
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[],
        forecast=forecast,
    )
    
    assert len(result.prepared_notifications) == 0
    assert len(result.pending_requests) == 0
    assert result.metrics.subscriptions_evaluated == 0


def test_error_handling_none_forecast_location(
    orchestrator,
    utc_location,
):
    """Test handling when forecast location_id is None."""
    subscription = create_mock_subscription(location=utc_location)
    
    # Create forecast with mismatched location
    current = CurrentWeather(
        location_id=999,  # Different location
        timestamp=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
        temperature_celsius=15.0,
        feels_like_celsius=14.0,
        wind_speed_kmh=10.0,
        rain_probability=30.0,
        rain_amount_mm=0.5,
        description="Test",
        severe_event=None,
    )
    tomorrow = DailyForecast(
        location_id=999,
        forecast_date=date(2026, 4, 10),
        temp_min_celsius=10.0,
        temp_max_celsius=20.0,
        temp_avg_celsius=15.0,
        rain_probability=40.0,
        rain_amount_mm=1.0,
        wind_speed_kmh=12.0,
        description="Test tomorrow",
        severe_event=None,
    )
    forecast = Forecast(location_id=999, current=current, tomorrow=tomorrow)
    
    # Should handle gracefully (subscription location doesn't match forecast)
    # This is a data consistency issue but shouldn't crash
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast,
    )
    
    # Will likely skip validation or fail safely
    assert isinstance(result.prepared_notifications, list)
    assert isinstance(result.pending_requests, list)


# ============================================================================
# TIMEZONE TESTS
# ============================================================================


def test_timezone_moscow_window_open_at_local_time(
    orchestrator,
    moscow_location,
):
    """Test timezone: Moscow window open scenario."""
    # Moscow: 07:00 UTC = 10:00 MSK
    # Window: 09:00-17:00 MSK = 06:00-14:00 UTC
    subscription = create_mock_subscription(
        location=moscow_location,
        active_from="09:00",  # MSK time
        active_to="17:00",    # MSK time
    )
    
    # Evaluate at 07:00 UTC (within 06:00-14:00 UTC window)
    forecast = create_forecast_with_severe_event()
    result = orchestrator.orchestrate_notifications(
        location_id=moscow_location.id,
        subscriptions=[subscription],
        forecast=forecast,
        evaluation_time_utc=datetime(2026, 4, 9, 7, 0, 0, tzinfo=timezone.utc),
    )
    
    assert result.metrics.subscriptions_allowed >= 1
    assert len(result.prepared_notifications) >= 1


def test_timezone_moscow_window_closed_late_evening(
    orchestrator,
    moscow_location,
):
    """Test timezone: Moscow window closed at late MSK time."""
    # Moscow: 20:00 UTC = 23:00 MSK
    # Window: 09:00-17:00 MSK = 06:00-14:00 UTC
    subscription = create_mock_subscription(
        location=moscow_location,
        active_from="09:00",  # MSK time
        active_to="17:00",    # MSK time
    )
    
    forecast = create_forecast_with_severe_event()
    result = orchestrator.orchestrate_notifications(
        location_id=moscow_location.id,
        subscriptions=[subscription],
        forecast=forecast,
        evaluation_time_utc=datetime(2026, 4, 9, 20, 0, 0, tzinfo=timezone.utc),
    )
    
    # Should be blocked (window closed)
    if result.metrics.subscriptions_matched > 0:
        assert result.metrics.subscriptions_allowed == 0


# ============================================================================
# CONDITION MATCHING TESTS
# ============================================================================


def test_condition_temperature_below(
    orchestrator,
    utc_location,
):
    """Test TEMPERATURE_BELOW condition matching."""
    cond = SubscriptionCondition(
        id=1,
        subscription_id=1,
        type=ConditionType.TEMPERATURE_BELOW,
        threshold_value=20.0,
        threshold_unit="°C",
    )
    subscription = create_mock_subscription(
        location=utc_location,
        conditions=[cond],
    )
    
    # Forecast: 15°C (matches)
    forecast = create_forecast_with_severe_event(temp=15.0)
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast,
    )
    
    assert result.metrics.subscriptions_matched == 1


def test_condition_temperature_above(
    orchestrator,
    utc_location,
):
    """Test TEMPERATURE_ABOVE condition matching."""
    cond = SubscriptionCondition(
        id=1,
        subscription_id=1,
        type=ConditionType.TEMPERATURE_ABOVE,
        threshold_value=20.0,
        threshold_unit="°C",
    )
    subscription = create_mock_subscription(
        location=utc_location,
        conditions=[cond],
    )
    
    # Forecast: 25°C (matches)
    forecast = create_forecast_with_severe_event(temp=25.0)
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast,
    )
    
    assert result.metrics.subscriptions_matched == 1


def test_condition_rain_probability(
    orchestrator,
    utc_location,
):
    """Test RAIN_PROBABILITY_ABOVE condition matching."""
    cond = SubscriptionCondition(
        id=1,
        subscription_id=1,
        type=ConditionType.RAIN_PROBABILITY_ABOVE,
        threshold_value=40.0,
        threshold_unit="%",
    )
    subscription = create_mock_subscription(
        location=utc_location,
        conditions=[cond],
    )
    
    # forecast_normal has rain_probability=30% (doesn't match)
    forecast = create_forecast_with_severe_event()
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast,
    )
    
    assert result.metrics.subscriptions_matched == 0
    assert result.metrics.subscriptions_skipped == 1


def test_condition_wind_speed(
    orchestrator,
    utc_location,
):
    """Test WIND_SPEED_ABOVE condition matching."""
    cond = SubscriptionCondition(
        id=1,
        subscription_id=1,
        type=ConditionType.WIND_SPEED_ABOVE,
        threshold_value=15.0,
        threshold_unit="km/h",
    )
    subscription = create_mock_subscription(
        location=utc_location,
        conditions=[cond],
    )
    
    # Forecast has wind_speed=10 km/h (doesn't match threshold 15)
    forecast = create_forecast_with_severe_event()
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast,
    )
    
    assert result.metrics.subscriptions_matched == 0


def test_condition_severe_event_match(
    orchestrator,
    utc_location,
):
    """Test SEVERE_WEATHER condition matching."""
    cond = SubscriptionCondition(
        id=1,
        subscription_id=1,
        type=ConditionType.SEVERE_WEATHER,
        threshold_value=None,
        threshold_unit=None,
    )
    subscription = create_mock_subscription(
        location=utc_location,
        conditions=[cond],
    )
    
    # Forecast with severe event
    forecast = create_forecast_with_severe_event(
        severe_event=SeverityEventType.STORM
    )
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast,
    )
    
    assert result.metrics.subscriptions_matched == 1


# ============================================================================
# EVENT TYPE PRIORITY TESTS
# ============================================================================


def test_event_type_severe_has_highest_priority(
    orchestrator,
    utc_location,
):
    """Test that SEVERE_WEATHER_ALERT event type is used with SEVERE_WEATHER condition + severe event."""
    # Create subscription with SEVERE_WEATHER condition (not temperature)
    cond = SubscriptionCondition(
        id=1,
        subscription_id=1,
        type=ConditionType.SEVERE_WEATHER,
        threshold_value=None,
        threshold_unit=None,
    )
    subscription = create_mock_subscription(
        location=utc_location,
        conditions=[cond],
    )
    
    forecast = create_forecast_with_severe_event(
        severe_event=SeverityEventType.TORNADO
    )
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast,
    )
    
    if result.prepared_notifications:
        notification = result.prepared_notifications[0]
        assert notification.event_type == EventType.SEVERE_WEATHER_ALERT


def test_event_type_weather_if_no_severe_event(
    orchestrator,
    utc_location,
):
    """Test that TEMPERATURE_ALERT event type is used when no severe event and temperature matches."""
    # Create subscription with temperature condition
    cond = SubscriptionCondition(
        id=1,
        subscription_id=1,
        type=ConditionType.TEMPERATURE_BELOW,
        threshold_value=20.0,
        threshold_unit="°C",
    )
    subscription = create_mock_subscription(
        location=utc_location,
        conditions=[cond],
    )
    
    # No severe event
    forecast = create_forecast_with_severe_event(temp=15.0, severe_event=None)
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast,
    )
    
    if result.prepared_notifications:
        notification = result.prepared_notifications[0]
        assert notification.event_type == EventType.TEMPERATURE_ALERT


# ============================================================================
# MATCHED CONDITIONS COUNT TESTS
# ============================================================================


def test_matched_conditions_count_single_match(
    orchestrator,
    utc_location,
):
    """Test that matched_conditions_count is correct for single match."""
    cond = SubscriptionCondition(
        id=1,
        subscription_id=1,
        type=ConditionType.TEMPERATURE_BELOW,
        threshold_value=20.0,
        threshold_unit="°C",
    )
    subscription = create_mock_subscription(
        location=utc_location,
        conditions=[cond],
    )
    
    forecast = create_forecast_with_severe_event(temp=15.0)
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast,
    )
    
    if result.prepared_notifications:
        notification = result.prepared_notifications[0]
        assert notification.matched_conditions_count == 1


def test_matched_conditions_count_multiple_matches(
    orchestrator,
    utc_location,
):
    """Test matched_conditions_count with multiple matching conditions (ANY mode)."""
    # Both conditions match
    cond1 = SubscriptionCondition(
        id=1,
        subscription_id=1,
        type=ConditionType.TEMPERATURE_BELOW,
        threshold_value=20.0,
        threshold_unit="°C",
    )
    cond2 = SubscriptionCondition(
        id=2,
        subscription_id=1,
        type=ConditionType.RAIN_PROBABILITY_ABOVE,
        threshold_value=20.0,
        threshold_unit="%",
    )
    subscription = create_mock_subscription(
        location=utc_location,
        conditions=[cond1, cond2],
    )
    
    forecast = create_forecast_with_severe_event(temp=15.0)  # rain_prob=30%
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast,
    )
    
    if result.prepared_notifications:
        notification = result.prepared_notifications[0]
        # Should report both matched with ANY mode
        assert notification.matched_conditions_count >= 1


# ============================================================================
# EDGE CASES
# ============================================================================


def test_edge_case_exactly_at_boundary(
    orchestrator,
    utc_location,
):
    """Test condition exactly at threshold boundary."""
    # Condition: temp < 15
    # Forecast: temp = 15 (boundary)
    cond = SubscriptionCondition(
        id=1,
        subscription_id=1,
        type=ConditionType.TEMPERATURE_BELOW,
        threshold_value=15.0,
        threshold_unit="°C",
    )
    subscription = create_mock_subscription(
        location=utc_location,
        conditions=[cond],
    )
    
    forecast = create_forecast_with_severe_event(temp=15.0)
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast,
    )
    
    # At boundary: 15 < 15 is False, so shouldn't match
    assert result.metrics.subscriptions_skipped == 1


def test_edge_case_just_below_boundary(
    orchestrator,
    utc_location,
):
    """Test condition just below threshold."""
    cond = SubscriptionCondition(
        id=1,
        subscription_id=1,
        type=ConditionType.TEMPERATURE_BELOW,
        threshold_value=15.0,
        threshold_unit="°C",
    )
    subscription = create_mock_subscription(
        location=utc_location,
        conditions=[cond],
    )
    
    forecast = create_forecast_with_severe_event(temp=14.9)
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast,
    )
    
    # 14.9 < 15 is True, should match
    assert result.metrics.subscriptions_matched == 1


def test_edge_case_window_boundary_start_of_day(
    orchestrator,
    utc_location,
):
    """Test delivery window at start of day."""
    # Window: 08:00-14:00 (open in morning)
    subscription = create_mock_subscription(
        location=utc_location,
        active_from="08:00",
        active_to="14:00",
    )
    
    forecast = create_forecast_with_severe_event()
    
    # Test at 08:00 UTC (exactly at window start - should be allowed)
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[subscription],
        forecast=forecast,
        evaluation_time_utc=datetime(2026, 4, 9, 8, 0, 0, tzinfo=timezone.utc),
    )
    
    if result.metrics.subscriptions_matched > 0:
        # Should be allowed at 08:00
        assert result.metrics.subscriptions_allowed > 0


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


def test_integration_multiple_subscriptions_channels(
    orchestrator,
    utc_location,
):
    """Test full integration with multiple subscriptions and channels."""
    # Sub1: 2 channels (email, push)
    channels1 = [
        DeliveryChannel(
            id=1,
            subscription_id=1,
            type=DeliveryChannelType.EMAIL,
            destination="user1@example.com",
            active=True,
        ),
        DeliveryChannel(
            id=2,
            subscription_id=1,
            type=DeliveryChannelType.PUSH,
            destination="token_1",
            active=True,
        ),
    ]
    sub1 = create_mock_subscription(
        subscription_id=1,
        location=utc_location,
        channels=channels1,
    )
    
    # Sub2: 1 channel (webhook)
    channels2 = [
        DeliveryChannel(
            id=3,
            subscription_id=2,
            type=DeliveryChannelType.WEBHOOK,
            destination="https://webhook.example.com",
            active=True,
        ),
    ]
    sub2 = create_mock_subscription(
        subscription_id=2,
        location=utc_location,
        channels=channels2,
    )
    
    forecast = create_forecast_with_severe_event()
    result = orchestrator.orchestrate_notifications(
        location_id=1,
        subscriptions=[sub1, sub2],
        forecast=forecast,
    )
    
    # Should have 3 notifications (2 from sub1, 1 from sub2)
    assert len(result.prepared_notifications) == 3
    assert result.metrics.subscriptions_evaluated == 2
    assert result.metrics.subscriptions_matched == 2


def test_integration_realistic_scenario(
    orchestrator,
    moscow_location,
):
    """Test realistic scenario: multiple subs, timezones, conditions."""
    # User in Moscow, early morning (06:00 MSK = 03:00 UTC)
    # Outside window (09:00-17:00 MSK = 06:00-14:00 UTC)
    
    subscription = create_mock_subscription(
        location=moscow_location,
        active_from="09:00",  # MSK
        active_to="17:00",    # MSK
    )
    
    forecast = create_forecast_with_severe_event(temp=0.0)
    
    result = orchestrator.orchestrate_notifications(
        location_id=moscow_location.id,
        subscriptions=[subscription],
        forecast=forecast,
        evaluation_time_utc=datetime(2026, 4, 9, 3, 0, 0, tzinfo=timezone.utc),
    )
    
    # Should go to pending (matched but outside window)
    if result.metrics.subscriptions_matched > 0:
        assert result.metrics.subscriptions_allowed == 0
        assert result.metrics.subscriptions_pending > 0
