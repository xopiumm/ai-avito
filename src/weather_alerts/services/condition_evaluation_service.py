"""Condition evaluation service for Weather Alerts.

This service evaluates whether weather conditions match subscription criteria.
It handles all supported condition types and produces evaluation results
suitable for orchestration and notification delivery.

Support condition types:
- temperature_below: Current temperature < threshold
- temperature_above: Current temperature > threshold
- rain_probability_above: Current rain probability > threshold
- wind_speed_above: Current wind speed > threshold
- severe_weather: Current or forecasted severe event matches type

Evaluation logic:
- Multiple conditions use ANY logic: if any condition matches, subscription matches
- Results contain matched conditions and event type for notification routing
- Testable interface: pure functions with explicit inputs/outputs
"""

from dataclasses import dataclass
from enum import Enum as PyEnum
from typing import List, Optional

from src.weather_alerts.adapters.weather_provider import (
    CurrentWeather,
    DailyForecast,
    Forecast,
    SeverityEventType,
)
from src.weather_alerts.domain.models.subscription import (
    ConditionType,
    SubscriptionCondition,
)


# ============================================================================
# RESULT MODELS - TESTABLE INTERFACES
# ============================================================================


class EventType(str, PyEnum):
    """Event type for notification routing.
    
    Determines which template and urgency level to use for notifications.
    """
    
    TEMPERATURE_ALERT = "temperature_alert"
    RAIN_ALERT = "rain_alert"
    WIND_ALERT = "wind_alert"
    SEVERE_WEATHER_ALERT = "severe_weather_alert"


@dataclass
class MatchedCondition:
    """Represents a single matched weather condition.
    
    Attributes:
        condition_id: Database ID of the subscription condition
        condition_type: Type of weather condition (temperature_below, etc.)
        threshold_value: Expected threshold (e.g., -10°C, 70%)
        threshold_unit: Unit of measurement (°C, %, km/h)
        actual_value: Actual weather value that triggered the condition
        actual_unit: Unit of actual value (should match threshold_unit)
        event_type: Derived event type for this condition (affects notification routing)
    """
    
    condition_id: int
    condition_type: ConditionType
    threshold_value: float
    threshold_unit: str
    actual_value: float
    actual_unit: str
    event_type: EventType


@dataclass
class ConditionEvaluationResult:
    """Result of evaluating a subscription's conditions against weather data.
    
    This is the primary interface for orchestrators to understand:
    - Whether any conditions were matched (matched=True means send notification)
    - Which specific conditions triggered (for logging, metrics, debugging)
    - What event type to use for notification (routing, templating, urgency)
    
    Attributes:
        subscription_id: ID of evaluated subscription
        matched: Whether any condition matched (ANY logic)
        matched_conditions: List of conditions that matched
        event_type: Primary event type (for notification routing):
            - If multiple conditions match, uses most severe type
            - If severe_weather matched, SEVERE_WEATHER_ALERT is primary
            - Order of severity: SEVERE_WEATHER > TEMPERATURE > RAIN > WIND
        evaluation_timestamp: When this evaluation was performed (UTC)
        weather_data_timestamp: When the weather data was sampled
    """
    
    subscription_id: int
    matched: bool
    matched_conditions: List[MatchedCondition]
    event_type: Optional[EventType]
    evaluation_timestamp: 'datetime'  # UTC
    weather_data_timestamp: Optional['datetime']  # UTC, from weather provider


# ============================================================================
# EVALUATION SERVICE
# ============================================================================


class ConditionEvaluationService:
    """Service for evaluating weather conditions against subscriptions.
    
    Pure business logic layer: takes subscription conditions and weather data,
    returns structured evaluation results. No side effects, fully testable.
    
    Usage:
        service = ConditionEvaluationService()
        result = service.evaluate_subscription(
            subscription_id=1,
            conditions=[...],  # From subscription.conditions
            forecast=forecast_obj,  # From weather_provider.get_forecast()
        )
        if result.matched:
            # Create notification
            # Use result.event_type for routing
            # Log result.matched_conditions for audit trail
    """
    
    def evaluate_subscription(
        self,
        subscription_id: int,
        conditions: List[SubscriptionCondition],
        forecast: Forecast,
    ) -> ConditionEvaluationResult:
        """Evaluate whether any subscription conditions match weather conditions.
        
        Args:
            subscription_id: ID of the subscription being evaluated
            conditions: List of subscription conditions to check
            forecast: Weather forecast data (current + tomorrow)
        
        Returns:
            ConditionEvaluationResult with matched conditions and event type
        
        Raises:
            ValueError: If conditions list is empty or forecast data is invalid
        """
        if not conditions:
            raise ValueError("Cannot evaluate subscription with empty conditions")
        
        if forecast is None or forecast.current is None:
            raise ValueError("Forecast data is required for evaluation")
        
        matched_conditions: List[MatchedCondition] = []
        
        # Evaluate each condition (ANY logic: stop on first match)
        for condition in conditions:
            matched = self._evaluate_single_condition(condition, forecast)
            if matched:
                matched_conditions.append(matched)
        
        # Determine if subscription matched and primary event type
        is_matched = len(matched_conditions) > 0
        primary_event_type = (
            self._determine_primary_event_type(matched_conditions)
            if is_matched
            else None
        )
        
        return ConditionEvaluationResult(
            subscription_id=subscription_id,
            matched=is_matched,
            matched_conditions=matched_conditions,
            event_type=primary_event_type,
            evaluation_timestamp=self._get_now_utc(),
            weather_data_timestamp=forecast.current.timestamp,
        )
    
    def _evaluate_single_condition(
        self,
        condition: SubscriptionCondition,
        forecast: Forecast,
    ) -> Optional[MatchedCondition]:
        """Evaluate a single condition against weather data.
        
        Returns:
            MatchedCondition if condition matched, None otherwise
        """
        condition_type = condition.type
        
        if condition_type == ConditionType.TEMPERATURE_BELOW:
            return self._check_temperature_below(condition, forecast)
        
        elif condition_type == ConditionType.TEMPERATURE_ABOVE:
            return self._check_temperature_above(condition, forecast)
        
        elif condition_type == ConditionType.RAIN_PROBABILITY_ABOVE:
            return self._check_rain_probability_above(condition, forecast)
        
        elif condition_type == ConditionType.WIND_SPEED_ABOVE:
            return self._check_wind_speed_above(condition, forecast)
        
        elif condition_type == ConditionType.SEVERE_WEATHER:
            return self._check_severe_weather(condition, forecast)
        
        else:
            raise ValueError(f"Unknown condition type: {condition_type}")
    
    def _check_temperature_below(
        self,
        condition: SubscriptionCondition,
        forecast: Forecast,
    ) -> Optional[MatchedCondition]:
        """Check if current temperature is below threshold.
        
        Uses current weather data. Threshold in °C.
        """
        threshold = condition.threshold_value  # °C
        actual = forecast.current.temperature_celsius
        
        if actual < threshold:
            return MatchedCondition(
                condition_id=condition.id,
                condition_type=condition.type,
                threshold_value=threshold,
                threshold_unit="°C",
                actual_value=actual,
                actual_unit="°C",
                event_type=EventType.TEMPERATURE_ALERT,
            )
        return None
    
    def _check_temperature_above(
        self,
        condition: SubscriptionCondition,
        forecast: Forecast,
    ) -> Optional[MatchedCondition]:
        """Check if current temperature is above threshold.
        
        Uses current weather data. Threshold in °C.
        """
        threshold = condition.threshold_value  # °C
        actual = forecast.current.temperature_celsius
        
        if actual > threshold:
            return MatchedCondition(
                condition_id=condition.id,
                condition_type=condition.type,
                threshold_value=threshold,
                threshold_unit="°C",
                actual_value=actual,
                actual_unit="°C",
                event_type=EventType.TEMPERATURE_ALERT,
            )
        return None
    
    def _check_rain_probability_above(
        self,
        condition: SubscriptionCondition,
        forecast: Forecast,
    ) -> Optional[MatchedCondition]:
        """Check if rain probability is above threshold.
        
        For "rain tomorrow" scenario, checks tomorrow's daily forecast.
        For current rain, checks current weather.
        
        Thresholds in % (0-100).
        """
        threshold = condition.threshold_value  # %
        
        # TODO: Implement logic to detect if this is "rain tomorrow" vs "rain now"
        # For now, use current rain probability. In future, could accept
        # a flag or use forecast_date from condition if stored.
        actual = forecast.current.rain_probability
        
        if actual > threshold:
            return MatchedCondition(
                condition_id=condition.id,
                condition_type=condition.type,
                threshold_value=threshold,
                threshold_unit="%",
                actual_value=actual,
                actual_unit="%",
                event_type=EventType.RAIN_ALERT,
            )
        return None
    
    def _check_wind_speed_above(
        self,
        condition: SubscriptionCondition,
        forecast: Forecast,
    ) -> Optional[MatchedCondition]:
        """Check if wind speed is above threshold.
        
        Uses current weather data. Threshold in km/h.
        """
        threshold = condition.threshold_value  # km/h
        actual = forecast.current.wind_speed_kmh
        
        if actual > threshold:
            return MatchedCondition(
                condition_id=condition.id,
                condition_type=condition.type,
                threshold_value=threshold,
                threshold_unit="km/h",
                actual_value=actual,
                actual_unit="km/h",
                event_type=EventType.WIND_ALERT,
            )
        return None
    
    def _check_severe_weather(
        self,
        condition: SubscriptionCondition,
        forecast: Forecast,
    ) -> Optional[MatchedCondition]:
        """Check if current or forecasted severe weather matches condition.
        
        Condition specifies which severe event type to watch for.
        Checks both current and tomorrow's forecast.
        
        Args:
            condition: Must have severity_event_type set
            forecast: Contains current weather and daily forecast
        
        Returns:
            MatchedCondition if severe weather matched, None otherwise
        """
        expected_event = condition.severity_event_type
        
        # Check current severe weather
        if forecast.current.severe_event == expected_event:
            return MatchedCondition(
                condition_id=condition.id,
                condition_type=condition.type,
                threshold_value=0,  # Not applicable for severe weather
                threshold_unit="",
                actual_value=0,
                actual_unit="",
                event_type=EventType.SEVERE_WEATHER_ALERT,
            )
        
        # Check tomorrow's severe weather
        if forecast.tomorrow.severe_event == expected_event:
            return MatchedCondition(
                condition_id=condition.id,
                condition_type=condition.type,
                threshold_value=0,
                threshold_unit="",
                actual_value=0,
                actual_unit="",
                event_type=EventType.SEVERE_WEATHER_ALERT,
            )
        
        return None
    
    def _determine_primary_event_type(
        self,
        matched_conditions: List[MatchedCondition],
    ) -> EventType:
        """Determine primary event type from matched conditions.
        
        If multiple conditions matched, selects the most severe event type
        using this priority order:
        1. SEVERE_WEATHER_ALERT (most urgent)
        2. TEMPERATURE_ALERT
        3. RAIN_ALERT
        4. WIND_ALERT (least urgent)
        
        Args:
            matched_conditions: Non-empty list of matched conditions
        
        Returns:
            Most severe event type from matched conditions
        """
        if not matched_conditions:
            raise ValueError("Cannot determine event type from empty conditions")
        
        # Priority order (higher index = higher priority)
        event_priorities = {
            EventType.WIND_ALERT: 0,
            EventType.RAIN_ALERT: 1,
            EventType.TEMPERATURE_ALERT: 2,
            EventType.SEVERE_WEATHER_ALERT: 3,
        }
        
        # Find the most severe event type present
        max_priority = max(
            event_priorities.get(mc.event_type, -1)
            for mc in matched_conditions
        )
        
        for event_type, priority in event_priorities.items():
            if priority == max_priority:
                return event_type
        
        # Fallback (should not reach here)
        return matched_conditions[0].event_type
    
    @staticmethod
    def _get_now_utc() -> 'datetime':
        """Get current UTC timestamp.
        
        Extracted for testability: tests can mock this method.
        """
        from datetime import datetime, timezone
        return datetime.now(timezone.utc)
