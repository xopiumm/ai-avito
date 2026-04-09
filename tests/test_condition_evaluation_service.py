"""Unit tests for ConditionEvaluationService.

Tests cover:
- All supported condition types
- ANY logic (multiple conditions)
- Event type determination (priority)
- Edge cases and error conditions
- Result structure and timestamps
"""

from datetime import datetime, timezone, date
from typing import List

import pytest

from src.weather_alerts.adapters.weather_provider import (
    CurrentWeather,
    DailyForecast,
    Forecast,
    SeverityEventType,
)
from src.weather_alerts.domain.models.subscription import (
    ConditionType,
    SeverityEventType as ModelSeverityEventType,
    SubscriptionCondition,
)
from src.weather_alerts.services.condition_evaluation_service import (
    ConditionEvaluationResult,
    ConditionEvaluationService,
    EventType,
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def evaluation_service():
    """Create a condition evaluation service instance."""
    return ConditionEvaluationService()


@pytest.fixture
def mock_current_weather():
    """Create mock current weather data."""
    return CurrentWeather(
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


@pytest.fixture
def mock_daily_forecast():
    """Create mock daily forecast data."""
    return DailyForecast(
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


@pytest.fixture
def mock_forecast(mock_current_weather, mock_daily_forecast):
    """Create complete forecast fixture."""
    return Forecast(
        location_id=1,
        current=mock_current_weather,
        tomorrow=mock_daily_forecast,
    )


def create_mock_condition(
    condition_id: int,
    condition_type: ConditionType,
    threshold_value: float = None,
    severity_event: ModelSeverityEventType = None,
) -> SubscriptionCondition:
    """Helper to create mock subscription condition."""
    condition = SubscriptionCondition(
        id=condition_id,
        subscription_id=1,
        type=condition_type,
        threshold_value=threshold_value,
        threshold_unit="°C" if "temperature" in condition_type else "%",
        severity_event_type=severity_event,
    )
    return condition


# ============================================================================
# TEMPERATURE TESTS
# ============================================================================


def test_temperature_below_matches(evaluation_service, mock_forecast):
    """Test temperature_below condition when temp is below threshold."""
    conditions = [
        create_mock_condition(
            condition_id=1,
            condition_type=ConditionType.TEMPERATURE_BELOW,
            threshold_value=20.0,  # Threshold 20°C, actual 15°C
        )
    ]
    
    result = evaluation_service.evaluate_subscription(
        subscription_id=1,
        conditions=conditions,
        forecast=mock_forecast,
    )
    
    assert result.matched is True
    assert len(result.matched_conditions) == 1
    assert result.matched_conditions[0].condition_type == ConditionType.TEMPERATURE_BELOW
    assert result.matched_conditions[0].actual_value == 15.0
    assert result.matched_conditions[0].threshold_value == 20.0
    assert result.event_type == EventType.TEMPERATURE_ALERT


def test_temperature_below_no_match(evaluation_service, mock_forecast):
    """Test temperature_below condition when temp is NOT below threshold."""
    conditions = [
        create_mock_condition(
            condition_id=1,
            condition_type=ConditionType.TEMPERATURE_BELOW,
            threshold_value=10.0,  # Threshold 10°C, actual 15°C
        )
    ]
    
    result = evaluation_service.evaluate_subscription(
        subscription_id=1,
        conditions=conditions,
        forecast=mock_forecast,
    )
    
    assert result.matched is False
    assert len(result.matched_conditions) == 0
    assert result.event_type is None


def test_temperature_above_matches(evaluation_service, mock_forecast):
    """Test temperature_above condition when temp is above threshold."""
    conditions = [
        create_mock_condition(
            condition_id=1,
            condition_type=ConditionType.TEMPERATURE_ABOVE,
            threshold_value=10.0,  # Threshold 10°C, actual 15°C
        )
    ]
    
    result = evaluation_service.evaluate_subscription(
        subscription_id=1,
        conditions=conditions,
        forecast=mock_forecast,
    )
    
    assert result.matched is True
    assert len(result.matched_conditions) == 1
    assert result.matched_conditions[0].condition_type == ConditionType.TEMPERATURE_ABOVE
    assert result.event_type == EventType.TEMPERATURE_ALERT


def test_temperature_above_no_match(evaluation_service, mock_forecast):
    """Test temperature_above condition when temp is NOT above threshold."""
    conditions = [
        create_mock_condition(
            condition_id=1,
            condition_type=ConditionType.TEMPERATURE_ABOVE,
            threshold_value=20.0,  # Threshold 20°C, actual 15°C
        )
    ]
    
    result = evaluation_service.evaluate_subscription(
        subscription_id=1,
        conditions=conditions,
        forecast=mock_forecast,
    )
    
    assert result.matched is False
    assert len(result.matched_conditions) == 0


# ============================================================================
# RAIN PROBABILITY TESTS
# ============================================================================


def test_rain_probability_above_matches(evaluation_service, mock_forecast):
    """Test rain_probability_above when rain probability exceeds threshold."""
    conditions = [
        create_mock_condition(
            condition_id=1,
            condition_type=ConditionType.RAIN_PROBABILITY_ABOVE,
            threshold_value=20.0,  # Threshold 20%, actual 30%
        )
    ]
    
    result = evaluation_service.evaluate_subscription(
        subscription_id=1,
        conditions=conditions,
        forecast=mock_forecast,
    )
    
    assert result.matched is True
    assert len(result.matched_conditions) == 1
    assert result.matched_conditions[0].condition_type == ConditionType.RAIN_PROBABILITY_ABOVE
    assert result.matched_conditions[0].actual_value == 30.0
    assert result.event_type == EventType.RAIN_ALERT


def test_rain_probability_above_no_match(evaluation_service, mock_forecast):
    """Test rain_probability_above when rain probability does not exceed threshold."""
    conditions = [
        create_mock_condition(
            condition_id=1,
            condition_type=ConditionType.RAIN_PROBABILITY_ABOVE,
            threshold_value=50.0,  # Threshold 50%, actual 30%
        )
    ]
    
    result = evaluation_service.evaluate_subscription(
        subscription_id=1,
        conditions=conditions,
        forecast=mock_forecast,
    )
    
    assert result.matched is False
    assert len(result.matched_conditions) == 0


# ============================================================================
# WIND SPEED TESTS
# ============================================================================


def test_wind_speed_above_matches(evaluation_service, mock_forecast):
    """Test wind_speed_above when wind speed exceeds threshold."""
    conditions = [
        create_mock_condition(
            condition_id=1,
            condition_type=ConditionType.WIND_SPEED_ABOVE,
            threshold_value=5.0,  # Threshold 5 km/h, actual 10 km/h
        )
    ]
    
    result = evaluation_service.evaluate_subscription(
        subscription_id=1,
        conditions=conditions,
        forecast=mock_forecast,
    )
    
    assert result.matched is True
    assert len(result.matched_conditions) == 1
    assert result.matched_conditions[0].condition_type == ConditionType.WIND_SPEED_ABOVE
    assert result.matched_conditions[0].actual_value == 10.0
    assert result.event_type == EventType.WIND_ALERT


def test_wind_speed_above_no_match(evaluation_service, mock_forecast):
    """Test wind_speed_above when wind speed does not exceed threshold."""
    conditions = [
        create_mock_condition(
            condition_id=1,
            condition_type=ConditionType.WIND_SPEED_ABOVE,
            threshold_value=20.0,  # Threshold 20 km/h, actual 10 km/h
        )
    ]
    
    result = evaluation_service.evaluate_subscription(
        subscription_id=1,
        conditions=conditions,
        forecast=mock_forecast,
    )
    
    assert result.matched is False
    assert len(result.matched_conditions) == 0


# ============================================================================
# SEVERE WEATHER TESTS
# ============================================================================


def test_severe_weather_matches_current(evaluation_service, mock_current_weather, mock_daily_forecast):
    """Test severe_weather condition when current weather has severe event."""
    # Create weather with storm
    current = CurrentWeather(
        location_id=1,
        timestamp=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
        temperature_celsius=15.0,
        feels_like_celsius=14.0,
        wind_speed_kmh=25.0,
        rain_probability=80.0,
        rain_amount_mm=5.0,
        description="Severe thunderstorm",
        severe_event=SeverityEventType.STORM,
    )
    forecast = Forecast(location_id=1, current=current, tomorrow=mock_daily_forecast)
    
    conditions = [
        create_mock_condition(
            condition_id=1,
            condition_type=ConditionType.SEVERE_WEATHER,
            severity_event=ModelSeverityEventType.STORM,
        )
    ]
    
    result = evaluation_service.evaluate_subscription(
        subscription_id=1,
        conditions=conditions,
        forecast=forecast,
    )
    
    assert result.matched is True
    assert len(result.matched_conditions) == 1
    assert result.event_type == EventType.SEVERE_WEATHER_ALERT


def test_severe_weather_matches_tomorrow(evaluation_service, mock_current_weather):
    """Test severe_weather condition when tomorrow's forecast has severe event."""
    # Create weather with hurricane tomorrow
    tomorrow = DailyForecast(
        location_id=1,
        forecast_date=date(2026, 4, 10),
        temp_min_celsius=10.0,
        temp_max_celsius=20.0,
        temp_avg_celsius=15.0,
        rain_probability=100.0,
        rain_amount_mm=50.0,
        wind_speed_kmh=80.0,
        description="Hurricane warning",
        severe_event=SeverityEventType.HURRICANE,
    )
    forecast = Forecast(location_id=1, current=mock_current_weather, tomorrow=tomorrow)
    
    conditions = [
        create_mock_condition(
            condition_id=1,
            condition_type=ConditionType.SEVERE_WEATHER,
            severity_event=ModelSeverityEventType.HURRICANE,
        )
    ]
    
    result = evaluation_service.evaluate_subscription(
        subscription_id=1,
        conditions=conditions,
        forecast=forecast,
    )
    
    assert result.matched is True
    assert result.event_type == EventType.SEVERE_WEATHER_ALERT


def test_severe_weather_no_match_wrong_type(evaluation_service, mock_current_weather, mock_daily_forecast):
    """Test severe_weather condition when event type doesn't match."""
    # Create weather with storm but looking for tornado
    current = CurrentWeather(
        location_id=1,
        timestamp=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
        temperature_celsius=15.0,
        feels_like_celsius=14.0,
        wind_speed_kmh=25.0,
        rain_probability=80.0,
        rain_amount_mm=5.0,
        description="Severe thunderstorm",
        severe_event=SeverityEventType.STORM,
    )
    forecast = Forecast(location_id=1, current=current, tomorrow=mock_daily_forecast)
    
    conditions = [
        create_mock_condition(
            condition_id=1,
            condition_type=ConditionType.SEVERE_WEATHER,
            severity_event=ModelSeverityEventType.TORNADO,  # Looking for tornado, not storm
        )
    ]
    
    result = evaluation_service.evaluate_subscription(
        subscription_id=1,
        conditions=conditions,
        forecast=forecast,
    )
    
    assert result.matched is False


def test_severe_weather_no_match_no_event(evaluation_service, mock_forecast):
    """Test severe_weather condition when there's no severe weather."""
    conditions = [
        create_mock_condition(
            condition_id=1,
            condition_type=ConditionType.SEVERE_WEATHER,
            severity_event=ModelSeverityEventType.TORNADO,
        )
    ]
    
    result = evaluation_service.evaluate_subscription(
        subscription_id=1,
        conditions=conditions,
        forecast=mock_forecast,
    )
    
    assert result.matched is False


# ============================================================================
# ANY LOGIC (MULTIPLE CONDITIONS) TESTS
# ============================================================================


def test_multiple_conditions_any_logic_first_matches(evaluation_service, mock_forecast):
    """Test ANY logic: first condition matches, should trigger."""
    conditions = [
        create_mock_condition(
            condition_id=1,
            condition_type=ConditionType.TEMPERATURE_BELOW,
            threshold_value=20.0,  # Matches: 15 < 20
        ),
        create_mock_condition(
            condition_id=2,
            condition_type=ConditionType.WIND_SPEED_ABOVE,
            threshold_value=50.0,  # Does not match: 10 < 50
        ),
    ]
    
    result = evaluation_service.evaluate_subscription(
        subscription_id=1,
        conditions=conditions,
        forecast=mock_forecast,
    )
    
    assert result.matched is True
    assert len(result.matched_conditions) == 1
    assert result.matched_conditions[0].condition_id == 1


def test_multiple_conditions_any_logic_second_matches(evaluation_service, mock_forecast):
    """Test ANY logic: second condition matches, should trigger."""
    conditions = [
        create_mock_condition(
            condition_id=1,
            condition_type=ConditionType.TEMPERATURE_ABOVE,
            threshold_value=20.0,  # Does not match: 15 < 20
        ),
        create_mock_condition(
            condition_id=2,
            condition_type=ConditionType.WIND_SPEED_ABOVE,
            threshold_value=5.0,  # Matches: 10 > 5
        ),
    ]
    
    result = evaluation_service.evaluate_subscription(
        subscription_id=1,
        conditions=conditions,
        forecast=mock_forecast,
    )
    
    assert result.matched is True
    assert len(result.matched_conditions) == 1
    assert result.matched_conditions[0].condition_id == 2


def test_multiple_conditions_any_logic_all_match(evaluation_service, mock_forecast):
    """Test ANY logic: all conditions match, should return all."""
    conditions = [
        create_mock_condition(
            condition_id=1,
            condition_type=ConditionType.TEMPERATURE_BELOW,
            threshold_value=20.0,  # Matches: 15 < 20
        ),
        create_mock_condition(
            condition_id=2,
            condition_type=ConditionType.WIND_SPEED_ABOVE,
            threshold_value=5.0,  # Matches: 10 > 5
        ),
    ]
    
    result = evaluation_service.evaluate_subscription(
        subscription_id=1,
        conditions=conditions,
        forecast=mock_forecast,
    )
    
    assert result.matched is True
    assert len(result.matched_conditions) == 2


def test_multiple_conditions_any_logic_none_match(evaluation_service, mock_forecast):
    """Test ANY logic: no conditions match, should not trigger."""
    conditions = [
        create_mock_condition(
            condition_id=1,
            condition_type=ConditionType.TEMPERATURE_ABOVE,
            threshold_value=20.0,  # Does not match: 15 < 20
        ),
        create_mock_condition(
            condition_id=2,
            condition_type=ConditionType.WIND_SPEED_ABOVE,
            threshold_value=50.0,  # Does not match: 10 < 50
        ),
    ]
    
    result = evaluation_service.evaluate_subscription(
        subscription_id=1,
        conditions=conditions,
        forecast=mock_forecast,
    )
    
    assert result.matched is False
    assert len(result.matched_conditions) == 0


# ============================================================================
# EVENT TYPE PRIORITY TESTS
# ============================================================================


def test_event_type_priority_severe_weather_highest(evaluation_service, mock_current_weather):
    """Test that SEVERE_WEATHER_ALERT has highest priority."""
    # Create weather with storm
    current = CurrentWeather(
        location_id=1,
        timestamp=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
        temperature_celsius=5.0,  # Cold!
        feels_like_celsius=0.0,
        wind_speed_kmh=25.0,  # Windy!
        rain_probability=80.0,
        rain_amount_mm=5.0,
        description="Severe thunderstorm",
        severe_event=SeverityEventType.STORM,
    )
    tomorrow = DailyForecast(
        location_id=1,
        forecast_date=date(2026, 4, 10),
        temp_min_celsius=0.0,
        temp_max_celsius=10.0,
        temp_avg_celsius=5.0,
        rain_probability=90.0,
        rain_amount_mm=20.0,
        wind_speed_kmh=30.0,
        description="Rain and wind",
    )
    forecast = Forecast(location_id=1, current=current, tomorrow=tomorrow)
    
    conditions = [
        # Multiple matching conditions
        create_mock_condition(
            condition_id=1,
            condition_type=ConditionType.TEMPERATURE_BELOW,
            threshold_value=10.0,  # Matches
        ),
        create_mock_condition(
            condition_id=2,
            condition_type=ConditionType.WIND_SPEED_ABOVE,
            threshold_value=5.0,  # Matches
        ),
        create_mock_condition(
            condition_id=3,
            condition_type=ConditionType.RAIN_PROBABILITY_ABOVE,
            threshold_value=50.0,  # Matches
        ),
        create_mock_condition(
            condition_id=4,
            condition_type=ConditionType.SEVERE_WEATHER,
            severity_event=ModelSeverityEventType.STORM,  # Matches
        ),
    ]
    
    result = evaluation_service.evaluate_subscription(
        subscription_id=1,
        conditions=conditions,
        forecast=forecast,
    )
    
    assert result.matched is True
    assert result.event_type == EventType.SEVERE_WEATHER_ALERT


def test_event_type_priority_temperature_over_rain_wind(evaluation_service, mock_forecast):
    """Test that TEMPERATURE_ALERT has priority over RAIN and WIND alerts."""
    conditions = [
        create_mock_condition(
            condition_id=1,
            condition_type=ConditionType.WIND_SPEED_ABOVE,
            threshold_value=5.0,  # Matches
        ),
        create_mock_condition(
            condition_id=2,
            condition_type=ConditionType.RAIN_PROBABILITY_ABOVE,
            threshold_value=20.0,  # Matches
        ),
        create_mock_condition(
            condition_id=3,
            condition_type=ConditionType.TEMPERATURE_BELOW,
            threshold_value=20.0,  # Matches
        ),
    ]
    
    result = evaluation_service.evaluate_subscription(
        subscription_id=1,
        conditions=conditions,
        forecast=mock_forecast,
    )
    
    assert result.matched is True
    assert result.event_type == EventType.TEMPERATURE_ALERT


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


def test_empty_conditions_raises_error(evaluation_service, mock_forecast):
    """Test that evaluating with no conditions raises ValueError."""
    with pytest.raises(ValueError, match="empty conditions"):
        evaluation_service.evaluate_subscription(
            subscription_id=1,
            conditions=[],
            forecast=mock_forecast,
        )


def test_none_forecast_raises_error(evaluation_service):
    """Test that None forecast raises ValueError."""
    conditions = [
        create_mock_condition(
            condition_id=1,
            condition_type=ConditionType.TEMPERATURE_BELOW,
            threshold_value=20.0,
        )
    ]
    
    with pytest.raises(ValueError, match="Forecast data is required"):
        evaluation_service.evaluate_subscription(
            subscription_id=1,
            conditions=conditions,
            forecast=None,
        )


# ============================================================================
# RESULT STRUCTURE TESTS
# ============================================================================


def test_result_contains_all_required_fields(evaluation_service, mock_forecast):
    """Test that result contains all required fields."""
    conditions = [
        create_mock_condition(
            condition_id=1,
            condition_type=ConditionType.TEMPERATURE_BELOW,
            threshold_value=20.0,
        )
    ]
    
    result = evaluation_service.evaluate_subscription(
        subscription_id=1,
        conditions=conditions,
        forecast=mock_forecast,
    )
    
    # Check all fields are present
    assert isinstance(result, ConditionEvaluationResult)
    assert result.subscription_id == 1
    assert isinstance(result.matched, bool)
    assert isinstance(result.matched_conditions, list)
    assert result.event_type is not None
    assert result.evaluation_timestamp is not None
    assert result.weather_data_timestamp is not None


def test_matched_condition_contains_all_required_fields(evaluation_service, mock_forecast):
    """Test that matched condition contains all tracking information."""
    conditions = [
        create_mock_condition(
            condition_id=1,
            condition_type=ConditionType.TEMPERATURE_BELOW,
            threshold_value=20.0,
        )
    ]
    
    result = evaluation_service.evaluate_subscription(
        subscription_id=1,
        conditions=conditions,
        forecast=mock_forecast,
    )
    
    matched = result.matched_conditions[0]
    assert matched.condition_id == 1
    assert matched.condition_type == ConditionType.TEMPERATURE_BELOW
    assert matched.threshold_value == 20.0
    assert matched.threshold_unit == "°C"
    assert matched.actual_value == 15.0
    assert matched.actual_unit == "°C"
    assert matched.event_type == EventType.TEMPERATURE_ALERT
