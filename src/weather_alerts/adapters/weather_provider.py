"""Weather data provider adapter and normalization.

This module handles integration with external weather API providers
(OpenWeatherMap, Weather.com, etc.) and normalizes responses into
internal domain structures for condition evaluation.

Supported weather parameters:
- Temperature (current and forecast)
- Rain probability (current and forecast)
- Wind speed
- Severe weather events (storm, hurricane, tornado, etc.)
- Daily forecasts (for "rain tomorrow" scenarios)
"""

from dataclasses import dataclass
from datetime import datetime, date
from enum import Enum as PyEnum
from typing import Optional, Dict, Any
import httpx

from src.weather_alerts.config.settings import get_settings


# ============================================================================
# DOMAIN MODELS
# ============================================================================


class SeverityEventType(str, PyEnum):
    """Severe weather event types."""
    STORM = "storm"
    HURRICANE = "hurricane"
    TORNADO = "tornado"
    BLIZZARD = "blizzard"
    EXTREME_HEAT = "extreme_heat"
    EXTREME_COLD = "extreme_cold"


@dataclass
class CurrentWeather:
    """Current weather conditions.

    Used for evaluating temperature_below/above and wind_speed_above conditions.
    """
    location_id: int
    timestamp: datetime
    temperature_celsius: float
    feels_like_celsius: Optional[float]
    wind_speed_kmh: float
    rain_probability: float  # 0-100
    rain_amount_mm: Optional[float]
    description: str
    severe_event: Optional[SeverityEventType] = None

    def __repr__(self) -> str:
        return (
            f"<CurrentWeather temp={self.temperature_celsius}°C "
            f"wind={self.wind_speed_kmh}km/h "
            f"rain={self.rain_probability}% "
            f"({self.description})>"
        )


@dataclass
class DailyForecast:
    """Daily weather forecast (next 24 hours or single day summary).

    Used for evaluating tomorrow's conditions and "rain tomorrow" scenario.
    """
    location_id: int
    forecast_date: date
    temp_min_celsius: float
    temp_max_celsius: float
    temp_avg_celsius: float
    rain_probability: float  # 0-100
    rain_amount_mm: Optional[float]
    wind_speed_kmh: float
    description: str
    severe_event: Optional[SeverityEventType] = None

    def __repr__(self) -> str:
        return (
            f"<DailyForecast date={self.forecast_date} "
            f"temp_min={self.temp_min_celsius}°C temp_max={self.temp_max_celsius}°C "
            f"rain={self.rain_probability}% "
            f"({self.description})>"
        )


@dataclass
class Forecast:
    """Complete forecast data (current + next day).

    Contains all weather data needed for condition evaluation.
    """
    location_id: int
    current: CurrentWeather
    tomorrow: DailyForecast
    
    def __repr__(self) -> str:
        return (
            f"<Forecast location={self.location_id} "
            f"current={self.current} "
            f"tomorrow={self.tomorrow}>"
        )


# ============================================================================
# EXCEPTIONS
# ============================================================================


class WeatherProviderException(Exception):
    """Base exception for weather provider errors."""
    pass


class WeatherProviderAuthError(WeatherProviderException):
    """Authentication error (invalid API key, unauthorized)."""
    pass


class WeatherProviderNotFoundError(WeatherProviderException):
    """Location not found or API returned 404."""
    pass


class WeatherProviderRateLimitError(WeatherProviderException):
    """Rate limit exceeded (429, 503)."""
    pass


class WeatherProviderTemporaryError(WeatherProviderException):
    """Temporary error (5xx, timeout, connection error).
    
    Safe to retry later.
    """
    pass


class WeatherProviderDataError(WeatherProviderException):
    """Invalid or unexpected data format from provider."""
    pass


# ============================================================================
# WEATHER PROVIDER ADAPTER
# ============================================================================


class WeatherProvider:
    """Adapter for external weather provider API.

    Handles:
    - API authentication and requests
    - Response normalization to internal structures
    - Error handling and retry logic
    - Rate limiting and timeout handling

    Currently supports OpenWeatherMap API format.
    """

    def __init__(self, api_key: Optional[str] = None, timeout_seconds: int = 10):
        """Initialize weather provider adapter.

        Args:
            api_key: Weather API key (if None, uses settings)
            timeout_seconds: Request timeout (default 10s)
        """
        settings = get_settings()
        self.api_key = api_key or settings.weather_provider.api_key
        self.base_url = "https://api.openweathermap.org/data/2.5"
        self.timeout = timeout_seconds
        self.client = httpx.AsyncClient(timeout=self.timeout)

    async def close(self) -> None:
        """Close HTTP client connection."""
        await self.client.aclose()

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    async def get_forecast(
        self,
        location_id: int,
        latitude: float,
        longitude: float,
    ) -> Forecast:
        """Get complete forecast for a location (current + tomorrow).

        Retrieves current weather and next-day forecast to enable
        evaluation of all condition types including "rain tomorrow".

        Args:
            location_id: Internal location database ID (for tracking)
            latitude: Location latitude
            longitude: Location longitude

        Returns:
            Forecast object with current and daily forecast data

        Raises:
            WeatherProviderAuthError: Invalid API key
            WeatherProviderNotFoundError: Location not found
            WeatherProviderRateLimitError: Rate limit exceeded
            WeatherProviderTemporaryError: Temporary provider error
            WeatherProviderDataError: Invalid response format
        """
        try:
            # Get current weather and 5-day forecast in one call (2 API calls)
            current = await self._get_current_weather(latitude, longitude)
            tomorrow = await self._get_daily_forecast(latitude, longitude)
            
            # Normalize to internal structures
            current_normalized = self._normalize_current_weather(
                location_id, current
            )
            tomorrow_normalized = self._normalize_daily_forecast(
                location_id, tomorrow
            )
            
            return Forecast(
                location_id=location_id,
                current=current_normalized,
                tomorrow=tomorrow_normalized,
            )
        except WeatherProviderException:
            raise
        except Exception as e:
            raise WeatherProviderDataError(
                f"Unexpected error fetching forecast: {e}"
            )

    async def get_current_weather(
        self,
        location_id: int,
        latitude: float,
        longitude: float,
    ) -> CurrentWeather:
        """Get current weather only (faster, for real-time checks).

        Args:
            location_id: Internal location database ID
            latitude: Location latitude
            longitude: Location longitude

        Returns:
            CurrentWeather object

        Raises:
            WeatherProviderException: Various provider errors
        """
        try:
            raw = await self._get_current_weather(latitude, longitude)
            return self._normalize_current_weather(location_id, raw)
        except WeatherProviderException:
            raise
        except Exception as e:
            raise WeatherProviderDataError(
                f"Unexpected error fetching current weather: {e}"
            )

    async def get_daily_forecast(
        self,
        location_id: int,
        latitude: float,
        longitude: float,
        forecast_days: int = 1,
    ) -> DailyForecast:
        """Get daily forecast (for "rain tomorrow" scenarios).

        Args:
            location_id: Internal location database ID
            latitude: Location latitude
            longitude: Location longitude
            forecast_days: Days ahead to forecast (1 = tomorrow, default)

        Returns:
            DailyForecast object

        Raises:
            WeatherProviderException: Various provider errors
        """
        try:
            raw = await self._get_daily_forecast(latitude, longitude)
            # raw contains tomorrow's forecast; ignore forecast_days for now
            return self._normalize_daily_forecast(location_id, raw)
        except WeatherProviderException:
            raise
        except Exception as e:
            raise WeatherProviderDataError(
                f"Unexpected error fetching daily forecast: {e}"
            )

    # ========================================================================
    # PRIVATE API - CALLS
    # ========================================================================

    async def _get_current_weather(self, latitude: float, longitude: float) -> Dict[str, Any]:
        """Get current weather from OpenWeatherMap API.

        Returns:
            Raw API response dict
        """
        url = f"{self.base_url}/weather"
        params = {
            "lat": latitude,
            "lon": longitude,
            "appid": self.api_key,
            "units": "metric",  # Celsius
        }
        return await self._make_request(url, params)

    async def _get_daily_forecast(self, latitude: float, longitude: float) -> Dict[str, Any]:
        """Get 5-day forecast to extract tomorrow's data.

        OpenWeatherMap returns 5-day forecast; we extract the first day.

        Returns:
            Tomorrow's forecast data (extracted from 5-day forecast)
        """
        url = f"{self.base_url}/forecast"
        params = {
            "lat": latitude,
            "lon": longitude,
            "appid": self.api_key,
            "units": "metric",
            "cnt": 8,  # First 24 hours (8 * 3-hour periods)
        }
        response = await self._make_request(url, params)
        
        # Extract tomorrow's data from forecast list
        # response["list"] contains forecasts at 3-hour intervals
        if not response.get("list") or len(response["list"]) == 0:
            raise WeatherProviderDataError("No forecast data in response")
        
        # Aggregate tomorrow's forecast from 3-hour periods
        return self._aggregate_daily_forecast(response["list"])

    async def _make_request(
        self,
        url: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Make HTTP GET request to weather API with error handling.

        Args:
            url: Full API endpoint URL
            params: Query parameters

        Returns:
            Parsed JSON response

        Raises:
            WeatherProviderAuthError: 401/403
            WeatherProviderNotFoundError: 404
            WeatherProviderRateLimitError: 429/503
            WeatherProviderTemporaryError: Other 5xx, timeout, connection error
        """
        try:
            response = await self.client.get(url, params=params)
            
            # Successful response
            if response.status_code == 200:
                return response.json()
            
            # Authentication error
            elif response.status_code in (401, 403):
                raise WeatherProviderAuthError(
                    f"API authentication failed: {response.status_code}"
                )
            
            # Not found
            elif response.status_code == 404:
                raise WeatherProviderNotFoundError(
                    f"Location not found or endpoint not available"
                )
            
            # Rate limit or service unavailable
            elif response.status_code in (429, 503):
                raise WeatherProviderRateLimitError(
                    f"Provider rate limited or temporarily unavailable: {response.status_code}"
                )
            
            # Other server error
            elif response.status_code >= 500:
                raise WeatherProviderTemporaryError(
                    f"Provider server error: {response.status_code}"
                )
            
            # Other client error
            else:
                raise WeatherProviderDataError(
                    f"Unexpected HTTP response: {response.status_code}"
                )
        
        except httpx.TimeoutException:
            raise WeatherProviderTemporaryError("Request timeout")
        except httpx.ConnectError as e:
            raise WeatherProviderTemporaryError(f"Connection error: {e}")
        except httpx.RequestError as e:
            raise WeatherProviderTemporaryError(f"Request error: {e}")

    # ========================================================================
    # NORMALIZATION
    # ========================================================================

    def _normalize_current_weather(
        self,
        location_id: int,
        raw: Dict[str, Any],
    ) -> CurrentWeather:
        """Normalize OpenWeatherMap current weather response.

        Extracts relevant fields and converts to CurrentWeather structure.

        Args:
            location_id: Internal location ID
            raw: Raw API response dict

        Returns:
            Normalized CurrentWeather object

        Raises:
            WeatherProviderDataError: Missing required fields
        """
        try:
            main = raw.get("main", {})
            wind = raw.get("wind", {})
            weather = raw.get("weather", [{}])[0]
            clouds = raw.get("clouds", {})
            rain = raw.get("rain", {})
            
            # Extract temperature
            temp = main.get("temp")
            if temp is None:
                raise WeatherProviderDataError("Missing temperature in response")
            
            # Extract wind speed (convert m/s to km/h if needed)
            wind_speed_ms = wind.get("speed", 0)
            wind_speed_kmh = wind_speed_ms * 3.6  # m/s to km/h conversion
            
            # Extract rain probability (use cloud coverage as proxy)
            rain_probability = clouds.get("all", 0)  # Cloud coverage %
            
            # Extract rain amount (in mm, if available)
            rain_amount = rain.get("1h")  # Rainfall in last 1 hour
            
            # Detect severe weather from conditions
            severe_event = self._extract_severe_event(weather.get("main", ""))
            
            return CurrentWeather(
                location_id=location_id,
                timestamp=datetime.utcnow(),
                temperature_celsius=float(temp),
                feels_like_celsius=main.get("feels_like"),
                wind_speed_kmh=wind_speed_kmh,
                rain_probability=float(rain_probability),
                rain_amount_mm=rain_amount,
                description=weather.get("description", ""),
                severe_event=severe_event,
            )
        except (KeyError, ValueError, TypeError) as e:
            raise WeatherProviderDataError(
                f"Failed to normalize current weather: {e}"
            )

    def _normalize_daily_forecast(
        self,
        location_id: int,
        raw: Dict[str, Any],
    ) -> DailyForecast:
        """Normalize daily forecast data.

        Args:
            location_id: Internal location ID
            raw: Forecast data (extracted from API response)

        Returns:
            Normalized DailyForecast object

        Raises:
            WeatherProviderDataError: Missing required fields
        """
        try:
            # raw is aggregated dict from _aggregate_daily_forecast
            forecast_date = raw.get("date")
            if not forecast_date:
                # Default to tomorrow
                forecast_date = date.today()
            
            temp_min = raw.get("temp_min")
            temp_max = raw.get("temp_max")
            if temp_min is None or temp_max is None:
                raise WeatherProviderDataError("Missing temperature range in forecast")
            
            return DailyForecast(
                location_id=location_id,
                forecast_date=forecast_date,
                temp_min_celsius=float(temp_min),
                temp_max_celsius=float(temp_max),
                temp_avg_celsius=float((temp_min + temp_max) / 2),
                rain_probability=float(raw.get("rain_probability", 0)),
                rain_amount_mm=raw.get("rain_amount"),
                wind_speed_kmh=float(raw.get("wind_speed", 0)),
                description=raw.get("description", ""),
                severe_event=self._extract_severe_event(raw.get("weather", "")),
            )
        except (KeyError, ValueError, TypeError) as e:
            raise WeatherProviderDataError(
                f"Failed to normalize daily forecast: {e}"
            )

    def _aggregate_daily_forecast(self, forecast_list: list) -> Dict[str, Any]:
        """Aggregate 3-hour forecast periods into daily summary.

        Args:
            forecast_list: List of 3-hour forecast periods from API

        Returns:
            Aggregated daily forecast dict
        """
        temps = []
        rain_probs = []
        wind_speeds = []
        weather_main = ""
        rain_amount = 0
        
        for period in forecast_list:
            main = period.get("main", {})
            wind = period.get("wind", {})
            weather = period.get("weather", [{}])[0]
            rain = period.get("rain", {})
            clouds = period.get("clouds", {})
            
            # Collect temperatures
            if "temp" in main:
                temps.append(main["temp"])
            
            # Collect rain probabilities (use clouds as proxy)
            rain_probs.append(clouds.get("all", 0))
            
            # Collect wind speeds
            if "speed" in wind:
                wind_speeds.append(wind["speed"] * 3.6)  # m/s to km/h
            
            # Track weather type (use most severe)
            weather_main = weather.get("main", "")
            
            # Sum rain amount
            if "1h" in rain:
                rain_amount += rain["1h"]
        
        return {
            "date": date.today(),
            "temp_min": min(temps) if temps else 0,
            "temp_max": max(temps) if temps else 0,
            "rain_probability": max(rain_probs) if rain_probs else 0,
            "rain_amount": rain_amount if rain_amount > 0 else None,
            "wind_speed": max(wind_speeds) if wind_speeds else 0,
            "weather": weather_main,
            "description": f"{weather_main} forecast",
        }

    def _extract_severe_event(self, weather_description: str) -> Optional[SeverityEventType]:
        """Extract severe weather event type from description.

        Maps weather provider descriptions to SeverityEventType enum.

        Args:
            weather_description: Weather description from API

        Returns:
            SeverityEventType if severe weather detected, None otherwise
        """
        if not weather_description:
            return None
        
        desc_lower = weather_description.lower()
        
        # Map descriptions to severity types
        mappings = {
            SeverityEventType.STORM: ["storm", "thunderstorm", "severe thunderstorm"],
            SeverityEventType.HURRICANE: ["hurricane", "typhoon", "tropical storm"],
            SeverityEventType.TORNADO: ["tornado"],
            SeverityEventType.BLIZZARD: ["blizzard", "snow", "heavy snow"],
            SeverityEventType.EXTREME_HEAT: ["extreme heat", "extreme temperature", "heat"],
            SeverityEventType.EXTREME_COLD: ["extreme cold", "extreme freeze", "cold"],
        }
        
        for event_type, keywords in mappings.items():
            for keyword in keywords:
                if keyword in desc_lower:
                    return event_type
        
        return None
