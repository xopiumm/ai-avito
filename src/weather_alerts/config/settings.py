"""Configuration settings for Weather Alerts service using Pydantic v2."""

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """PostgreSQL database configuration."""

    url: str = Field(
        default="postgresql+asyncpg://weather_user:weather_pass@localhost:5432/weather_alerts",
        description="PostgreSQL connection URL with asyncpg driver",
    )
    echo: bool = Field(
        default=False,
        description="Enable SQLAlchemy SQL echo for debugging",
    )
    pool_size: int = Field(
        default=20,
        description="Database connection pool size",
    )
    max_overflow: int = Field(
        default=10,
        description="Maximum overflow connections beyond pool size",
    )

    model_config = SettingsConfigDict(env_prefix="DB_")


class RedisSettings(BaseSettings):
    """Redis configuration."""

    url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )
    dedup_ttl_seconds: int = Field(
        default=43200,
        description="TTL for deduplication keys (12 hours)",
    )
    socket_timeout: int = Field(
        default=5,
        description="Socket timeout in seconds",
    )

    model_config = SettingsConfigDict(env_prefix="REDIS_")


class WeatherProviderSettings(BaseSettings):
    """External weather provider configuration."""

    base_url: str = Field(
        default="https://api.openweathermap.org/data/2.5",
        description="Weather provider API base URL",
    )
    api_key: str = Field(
        default="your-api-key-here",
        description="Weather provider API key",
    )
    timeout_seconds: int = Field(
        default=10,
        description="Request timeout in seconds",
    )
    retry_attempts: int = Field(
        default=3,
        description="Number of retry attempts for failed requests",
    )

    model_config = SettingsConfigDict(env_prefix="WEATHER_PROVIDER_")


class EmailSettings(BaseSettings):
    """Email delivery configuration."""

    provider_url: str = Field(
        default="https://api.mailgun.net",
        description="Email provider API URL (e.g., Mailgun, SendGrid)",
    )
    api_key: str = Field(
        default="your-email-api-key",
        description="Email provider API key",
    )
    from_address: str = Field(
        default="alerts@weather-service.local",
        description="From address for email notifications",
    )
    timeout_seconds: int = Field(
        default=10,
        description="Request timeout in seconds",
    )

    model_config = SettingsConfigDict(env_prefix="EMAIL_")


class PushSettings(BaseSettings):
    """Push notification delivery configuration."""

    provider_url: str = Field(
        default="https://api.pushservice.local",
        description="Push provider API URL",
    )
    api_key: str = Field(
        default="your-push-api-key",
        description="Push provider API key",
    )
    timeout_seconds: int = Field(
        default=10,
        description="Request timeout in seconds",
    )

    model_config = SettingsConfigDict(env_prefix="PUSH_")


class WebhookSettings(BaseSettings):
    """Webhook delivery configuration."""

    delivery_timeout_seconds: int = Field(
        default=30,
        description="Timeout for webhook HTTP requests",
    )
    max_retries: int = Field(
        default=5,
        description="Maximum number of retry attempts for webhook delivery",
    )
    retry_backoff_seconds: int = Field(
        default=1,
        description="Initial backoff duration in seconds (exponential)",
    )

    model_config = SettingsConfigDict(env_prefix="WEBHOOK_")


class CelerySettings(BaseSettings):
    """Celery task queue configuration."""

    broker_url: str = Field(
        default="redis://localhost:6379/1",
        description="Celery broker URL (Redis)",
    )
    result_backend: str = Field(
        default="redis://localhost:6379/2",
        description="Celery result backend URL (Redis)",
    )
    task_track_started: bool = Field(
        default=True,
        description="Track task started state",
    )
    task_time_limit: int = Field(
        default=3600,
        description="Hard time limit for tasks in seconds (1 hour)",
    )
    task_soft_time_limit: int = Field(
        default=3000,
        description="Soft time limit for tasks in seconds (50 minutes)",
    )

    model_config = SettingsConfigDict(env_prefix="CELERY_")


class APISettings(BaseSettings):
    """FastAPI and application configuration."""

    host: str = Field(
        default="0.0.0.0",
        description="API server bind address",
    )
    port: int = Field(
        default=8000,
        description="API server port",
    )
    title: str = Field(
        default="Weather Alerts API",
        description="API title",
    )
    version: str = Field(
        default="1.0.0",
        description="API version",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    request_timeout_seconds: int = Field(
        default=30,
        description="Default request timeout in seconds",
    )
    allow_dev_auth: bool = Field(
        default=False,
        description="Allow dev mode authentication (returns test_user without token validation); only enable in development",
    )

    model_config = SettingsConfigDict(env_prefix="API_")


class Settings(BaseSettings):
    """Root settings combining all configuration sections."""

    environment: str = Field(
        default="development",
        description="Deployment environment (development, staging, production)",
    )

    # Subsettings
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    weather_provider: WeatherProviderSettings = Field(
        default_factory=WeatherProviderSettings
    )
    email: EmailSettings = Field(default_factory=EmailSettings)
    push: PushSettings = Field(default_factory=PushSettings)
    webhook: WebhookSettings = Field(default_factory=WebhookSettings)
    celery: CelerySettings = Field(default_factory=CelerySettings)
    api: APISettings = Field(default_factory=APISettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


# Global settings instance (lazy-loaded on first access)
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Force reload settings from environment (useful for testing)."""
    global _settings
    _settings = Settings()
    return _settings
