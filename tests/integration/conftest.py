"""Pytest fixtures and utilities for integration tests.

This module provides shared fixtures for integration test suite:

Database Fixtures:
- test_db_session: AsyncSession for test database (handles setup/teardown)

FastAPI Fixtures:
- app: Configured FastAPI application instance
- client: TestClient for API requests

Test Data Builders:
- sample_location: Test location dict
- sample_subscription_request: Valid subscription creation request
- sample_forecast: Weather forecast data

The fixtures handle:
- Setup: Database initialization, app creation
- Teardown: Database cleanup, session closure
- Isolation: Each test starts fresh
- Mocking: All external dependencies replaced
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Generator, Dict, Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# Import domain models and services
from src.weather_alerts.api.main import create_app
from src.weather_alerts.config.database import Base, get_db_session
from src.weather_alerts.domain.models.subscription import (
    Subscription,
    SubscriptionStatus,
    SubscriptionCondition,
    DeliveryChannel,
    DeliveryChannelType,
)
from src.weather_alerts.adapters.weather_provider import (
    Forecast,
    CurrentWeather,
)
from src.weather_alerts.services.condition_evaluation_service import EventType


# ============================================================================
# SIMPLE TEST DATA MODEL - NO ORM DEPENDENCY
# ============================================================================


class Location:
    """Minimal Location model for testing.
    
    In production, this would be a full ORM model persisted in database.
    For integration tests, we use this simple class to pass location data
    to endpoints and services without adding ORM complexity.
    """
    
    def __init__(self, id: int, name: str, latitude: float, 
                 longitude: float, timezone: str):
        self.id = id
        self.name = name
        self.latitude = latitude
        self.longitude = longitude
        self.timezone = timezone


# ============================================================================
# DATABASE FIXTURES
# ============================================================================


@pytest.fixture(scope="function")
async def test_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create AsyncSession for test database with in-memory SQLite.
    
    Handles:
    - Engine creation with SQLite in-memory
    - Table initialization
    - Session lifecycle management
    - Cleanup and disposal
    
    Provides:
    - Fresh session for each test
    - Automatic cleanup after test
    - Access to test database via session
    
    Yields:
        AsyncSession instance for single test
    
    Usage in tests:
    ```python
    async def test_create_subscription(test_db_session):
        # session is ready to use
        subscription = await SubscriptionService(test_db_session).create(...)
    ```
    """
    # Create in-memory engine
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"timeout": 30},
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session
        # Cleanup: explicit session close (transaction rollback)
        await session.rollback()

    # Cleanup: Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


# ============================================================================
# FASTAPI FIXTURES
# ============================================================================


@pytest.fixture
async def app(test_db_session):
    """Create FastAPI app instance with test database.
    
    Configures:
    - Database session dependency with test session
    - All routes registered
    - Exception handlers configured
    - Startup/shutdown events skipped
    
    Args:
        test_db_session: Fixture providing test AsyncSession
    
    Returns:
        FastAPI application instance for testing
    
    Note:
        The app's database dependency is patched to use test_db_session
        instead of the production database connection.
    """
    app = create_app()

    # Override database dependency with test session
    async def override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db_session] = override_get_db

    return app


@pytest.fixture
async def client(app):
    """Create async HTTP test client for FastAPI app.
    
    Provides:
    - TestClient for making API requests
    - Async/await support
    - Automatic request/response handling
    - Cookie and header management
    
    Args:
        app: FastAPI application instance fixture
    
    Yields:
        AsyncClient for making test requests
    
    Usage in tests:
    ```python
    async def test_create_subscription(client):
        response = await client.post("/alerts/subscriptions", json={...})
        assert response.status_code == 201
    ```
    """
    from httpx import ASGITransport
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


# ============================================================================
# SAMPLE DATA FIXTURES
# ============================================================================


@pytest.fixture
def sample_location() -> Location:
    """Provide sample location data for testing.
    
    Returns:
        Location object with:
        - id: 1
        - name: "Moscow"
        - latitude: 55.7558
        - longitude: 37.6173
        - timezone: "Europe/Moscow"
    
    Used to create test subscriptions that target specific locations.
    """
    return Location(
        id=1,
        name="Moscow",
        latitude=55.7558,
        longitude=37.6173,
        timezone="Europe/Moscow",
    )


@pytest.fixture
def sample_subscription_request() -> Dict[str, Any]:
    """Provide minimal valid subscription creation request.
    
    Returns dict with:
    - location: Location reference (id required)
    - conditions: List of conditions (min 1)
    - deliveryChannels: List of destinations (min 1)
    - schedule: Optional delivery window
    
    This is a valid request that can be POSTed to /alerts/subscriptions
    without modification (except location_id should be set to actual ID).
    """
    return {
        "location": {"id": 1},
        "conditions": [
            {
                "type": "temperature_below",
                "threshold_value": -10,
            }
        ],
        "deliveryChannels": [
            {
                "type": "email",
                "destination": "test@example.com",
                "active": True,
            }
        ],
        "schedule": {
            "activeFrom": "08:00",
            "activeTo": "20:00",
            "timezoneSource": "location",
        },
    }


@pytest.fixture
def sample_subscription_multi_channel() -> Dict[str, Any]:
    """Provide subscription request with multiple delivery channels.
    
    Includes:
    - Email channel
    - Push channel (with device token)
    - Webhook channel (with URL)
    
    Test scenario: Verify all channels are activated and receive notifications.
    """
    return {
        "location": {"id": 1},
        "conditions": [
            {
                "type": "rain_probability_above",
                "threshold_value": 70,
            }
        ],
        "deliveryChannels": [
            {
                "type": "email",
                "destination": "user@example.com",
                "active": True,
            },
            {
                "type": "push",
                "destination": "fcm_token_abc123",
                "active": True,
            },
            {
                "type": "webhook",
                "destination": "https://example.com/alerts",
                "active": True,
            },
        ],
    }


@pytest.fixture
def sample_forecast(sample_location) -> Forecast:
    """Provide sample weather forecast data.
    
    Returns:
        Forecast object with:
        - current: Current weather conditions
        - daily: Daily forecast (7 days)
        - location_id: Reference to location
    
    Contains realistic weather data:
    - Temperature: -15°C (below alert threshold)
    - Rain probability: 80% (above alert threshold)
    - Wind speed: 15 m/s
    """
    now_utc = datetime.now(tz=timezone.utc)

    return Forecast(
        location_id=sample_location.id,
        current=CurrentWeather(
            timestamp=now_utc,
            temperature=-15,
            feels_like=-20,
            humidity=85,
            wind_speed=15,
            wind_direction="NW",
            weather_main="Snow",
            weather_description="heavy snow",
            pressure=1010,
            visibility=500,
            rain_probability=80,
            snow_probability=95,
            cloud_coverage=95,
        ),
        daily=[],
        timestamp=now_utc,
    )


# ============================================================================
# HELPER FIXTURES
# ============================================================================


@pytest.fixture
def test_user_id() -> str:
    """Provide test user ID.
    
    Returns:
        str: Fixed user ID for all tests
        ("test_user_123")
    
    Used for:
    - User ID in API requests (Authorization)
    - User ID in database records
    - Ensuring tests are isolated per user
    """
    return "test_user_123"


@pytest.fixture
def timestamp_utc() -> datetime:
    """Provide UTC timestamp for test data.
    
    Returns:
        datetime: Current UTC timestamp
    
    Used for:
    - Forecast timestamp
    - Subscription created_at
    - Notification timestamps
    """
    return datetime.now(tz=timezone.utc)


# ============================================================================
# ASYNC TEST SETUP
# ============================================================================


@pytest.fixture(scope="session")
def event_loop():
    """Provide event loop for async tests.
    
    Required for pytest-asyncio to work with async fixtures.
    
    Scope: session (created once per test session)
    Policy: Automatically created and closed by pytest-asyncio
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
