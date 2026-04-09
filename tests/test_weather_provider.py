"""Tests for weather provider adapter."""

import pytest
from datetime import datetime, date

from src.weather_alerts.adapters import (
    WeatherProvider,
    CurrentWeather,
    DailyForecast,
    Forecast,
    SeverityEventType,
    WeatherProviderException,
    WeatherProviderAuthError,
    WeatherProviderNotFoundError,
    WeatherProviderDataError,
)


class TestSeverityEventType:
    """Test severity event type enum."""
    
    def test_enum_values(self):
        """Test that all severity event types are defined."""
        assert SeverityEventType.STORM.value == "storm"
        assert SeverityEventType.HURRICANE.value == "hurricane"
        assert SeverityEventType.TORNADO.value == "tornado"
        assert SeverityEventType.BLIZZARD.value == "blizzard"
        assert SeverityEventType.EXTREME_HEAT.value == "extreme_heat"
        assert SeverityEventType.EXTREME_COLD.value == "extreme_cold"


class TestCurrentWeather:
    """Test CurrentWeather data class."""
    
    def test_creation(self):
        """Test creating CurrentWeather instance."""
        weather = CurrentWeather(
            location_id=1,
            timestamp=datetime.utcnow(),
            temperature_celsius=25.0,
            feels_like_celsius=23.0,
            wind_speed_kmh=10.0,
            rain_probability=50.0,
            rain_amount_mm=5.0,
            description="Cloudy with rain",
        )
        assert weather.location_id == 1
        assert weather.temperature_celsius == 25.0
        assert weather.wind_speed_kmh == 10.0
        assert weather.rain_probability == 50.0
    
    def test_with_severe_event(self):
        """Test CurrentWeather with severe event."""
        weather = CurrentWeather(
            location_id=1,
            timestamp=datetime.utcnow(),
            temperature_celsius=35.0,
            feels_like_celsius=35.0,
            wind_speed_kmh=50.0,
            rain_probability=90.0,
            rain_amount_mm=None,
            description="Severe thunderstorm",
            severe_event=SeverityEventType.STORM,
        )
        assert weather.severe_event == SeverityEventType.STORM


class TestDailyForecast:
    """Test DailyForecast data class."""
    
    def test_creation(self):
        """Test creating DailyForecast instance."""
        forecast = DailyForecast(
            location_id=1,
            forecast_date=date.today(),
            temp_min_celsius=15.0,
            temp_max_celsius=25.0,
            temp_avg_celsius=20.0,
            rain_probability=30.0,
            rain_amount_mm=2.0,
            wind_speed_kmh=8.0,
            description="Partly cloudy",
        )
        assert forecast.location_id == 1
        assert forecast.temp_min_celsius == 15.0
        assert forecast.temp_max_celsius == 25.0
        assert forecast.temp_avg_celsius == 20.0


class TestForecast:
    """Test Forecast combining current and daily forecast."""
    
    def test_creation(self):
        """Test creating Forecast instance."""
        current = CurrentWeather(
            location_id=1,
            timestamp=datetime.utcnow(),
            temperature_celsius=20.0,
            feels_like_celsius=19.0,
            wind_speed_kmh=5.0,
            rain_probability=20.0,
            rain_amount_mm=None,
            description="Clear",
        )
        tomorrow = DailyForecast(
            location_id=1,
            forecast_date=date.today(),
            temp_min_celsius=15.0,
            temp_max_celsius=25.0,
            temp_avg_celsius=20.0,
            rain_probability=30.0,
            rain_amount_mm=2.0,
            wind_speed_kmh=8.0,
            description="Partly cloudy",
        )
        forecast = Forecast(location_id=1, current=current, tomorrow=tomorrow)
        assert forecast.location_id == 1
        assert forecast.current.temperature_celsius == 20.0
        assert forecast.tomorrow.rain_probability == 30.0


class TestWeatherProviderExceptions:
    """Test exception hierarchy."""
    
    def test_exception_inheritance(self):
        """Test that specific exceptions inherit from base."""
        assert issubclass(WeatherProviderAuthError, WeatherProviderException)
        assert issubclass(WeatherProviderNotFoundError, WeatherProviderException)
        assert issubclass(WeatherProviderDataError, WeatherProviderException)
    
    def test_raise_auth_error(self):
        """Test raising auth error."""
        with pytest.raises(WeatherProviderAuthError):
            raise WeatherProviderAuthError("Invalid API key")
    
    def test_raise_not_found_error(self):
        """Test raising not found error."""
        with pytest.raises(WeatherProviderNotFoundError):
            raise WeatherProviderNotFoundError("Location not found")


class TestWeatherProviderNormalization:
    """Test data normalization logic."""
    
    def test_extract_severe_event_storm(self):
        """Test extraction of storm event."""
        provider = WeatherProvider()
        assert provider._extract_severe_event("Thunderstorm") == SeverityEventType.STORM
        assert provider._extract_severe_event("Severe thunderstorm") == SeverityEventType.STORM
    
    def test_extract_severe_event_hurricane(self):
        """Test extraction of hurricane event."""
        provider = WeatherProvider()
        assert provider._extract_severe_event("Hurricane") == SeverityEventType.HURRICANE
        assert provider._extract_severe_event("Typhoon") == SeverityEventType.HURRICANE
    
    def test_extract_severe_event_tornado(self):
        """Test extraction of tornado event."""
        provider = WeatherProvider()
        assert provider._extract_severe_event("Tornado") == SeverityEventType.TORNADO
    
    def test_extract_severe_event_blizzard(self):
        """Test extraction of blizzard event."""
        provider = WeatherProvider()
        assert provider._extract_severe_event("Blizzard") == SeverityEventType.BLIZZARD
        assert provider._extract_severe_event("Heavy snow") == SeverityEventType.BLIZZARD
    
    def test_extract_severe_event_extreme_heat(self):
        """Test extraction of extreme heat event."""
        provider = WeatherProvider()
        assert provider._extract_severe_event("Extreme heat") == SeverityEventType.EXTREME_HEAT
    
    def test_extract_severe_event_extreme_cold(self):
        """Test extraction of extreme cold event."""
        provider = WeatherProvider()
        assert provider._extract_severe_event("Extreme cold") == SeverityEventType.EXTREME_COLD
    
    def test_extract_severe_event_none(self):
        """Test no severe event detected."""
        provider = WeatherProvider()
        assert provider._extract_severe_event("Clear sky") is None
        assert provider._extract_severe_event("") is None
    
    def test_normalize_current_weather_valid(self):
        """Test normalizing valid current weather response."""
        provider = WeatherProvider()
        raw = {
            "main": {
                "temp": 25.5,
                "feels_like": 24.0,
            },
            "wind": {
                "speed": 2.5,  # m/s
            },
            "clouds": {
                "all": 50,  # Cloud coverage %
            },
            "rain": {
                "1h": 5.0,
            },
            "weather": [
                {
                    "main": "Clouds",
                    "description": "overcast clouds",
                }
            ],
        }
        weather = provider._normalize_current_weather(1, raw)
        assert weather.location_id == 1
        assert weather.temperature_celsius == 25.5
        assert weather.feels_like_celsius == 24.0
        assert weather.wind_speed_kmh == 9.0  # 2.5 m/s * 3.6
        assert weather.rain_probability == 50.0
        assert weather.rain_amount_mm == 5.0
    
    def test_normalize_current_weather_missing_temp(self):
        """Test error on missing temperature."""
        provider = WeatherProvider()
        raw = {
            "main": {},
            "wind": {"speed": 0},
            "clouds": {"all": 0},
            "weather": [{}],
        }
        with pytest.raises(WeatherProviderDataError):
            provider._normalize_current_weather(1, raw)
    
    def test_normalize_daily_forecast_valid(self):
        """Test normalizing valid daily forecast."""
        provider = WeatherProvider()
        raw = {
            "date": date.today(),
            "temp_min": 15.0,
            "temp_max": 25.0,
            "rain_probability": 40.0,
            "rain_amount": 3.0,
            "wind_speed": 8.0,
            "weather": "Clouds",
            "description": "Partly cloudy",
        }
        forecast = provider._normalize_daily_forecast(1, raw)
        assert forecast.location_id == 1
        assert forecast.temp_min_celsius == 15.0
        assert forecast.temp_max_celsius == 25.0
        assert forecast.temp_avg_celsius == 20.0
        assert forecast.rain_probability == 40.0
    
    def test_aggregate_daily_forecast(self):
        """Test aggregating 3-hour forecast periods."""
        provider = WeatherProvider()
        forecast_list = [
            {
                "main": {"temp": 20.0},
                "wind": {"speed": 2.0},
                "clouds": {"all": 30},
                "weather": [{"main": "Clouds"}],
                "rain": {},
            },
            {
                "main": {"temp": 22.0},
                "wind": {"speed": 3.0},
                "clouds": {"all": 40},
                "weather": [{"main": "Rain"}],
                "rain": {"1h": 2.0},
            },
        ]
        aggregated = provider._aggregate_daily_forecast(forecast_list)
        assert aggregated["temp_min"] == 20.0
        assert aggregated["temp_max"] == 22.0
        assert aggregated["wind_speed"] == 10.8  # 3.0 * 3.6
        assert aggregated["rain_amount"] == 2.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
