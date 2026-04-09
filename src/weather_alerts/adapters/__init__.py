"""External service adapters (weather provider, email, push, webhook)."""

from .weather_provider import (
    WeatherProvider,
    CurrentWeather,
    DailyForecast,
    Forecast,
    SeverityEventType,
    WeatherProviderException,
    WeatherProviderAuthError,
    WeatherProviderNotFoundError,
    WeatherProviderRateLimitError,
    WeatherProviderTemporaryError,
    WeatherProviderDataError,
)

__all__ = [
    "CurrentWeather",
    "DailyForecast",
    "Forecast",
    "SeverityEventType",
    "WeatherProvider",
    "WeatherProviderAuthError",
    "WeatherProviderDataError",
    "WeatherProviderException",
    "WeatherProviderNotFoundError",
    "WeatherProviderRateLimitError",
    "WeatherProviderTemporaryError",
]
