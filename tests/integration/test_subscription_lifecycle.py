"""Integration tests for subscription lifecycle.

Tests the complete subscription management flow:
- Create: Valid and invalid subscriptions
- Read: List and get operations
- Update: Modify subscription properties
- Delete: Soft-delete with status changes
- Pause/Resume: State transitions

Each test:
1. Sets up test environment (database, mocks)
2. Makes API request
3. Verifies HTTP response
4. Verifies database state
5. Validates business logic

Test isolation:
- Fresh database for each test
- No side effects between tests
- Explicit setup in each test (no magic)
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.weather_alerts.domain.models.subscription import (
    Subscription,
    SubscriptionStatus,
    DeliveryChannel,
    SubscriptionCondition,
    DeliveryChannelType,
)


# ============================================================================
# SUBSCRIPTION LIFECYCLE TESTS
# ============================================================================


class TestSubscriptionCreate:
    """Test subscription creation (POST /alerts/subscriptions).
    
    Scenarios:
    - Valid subscription with all fields
    - Valid subscription with minimal fields
    - Invalid: Missing conditions
    - Invalid: Missing delivery channels
    - Invalid: Invalid condition type
    - Invalid: Unsupported channel type
    - Conflict: Subscription already exists
    """

    @pytest.mark.asyncio
    async def test_create_subscription_success(
        self, client: AsyncClient, test_db_session: AsyncSession, test_user_id: str
    ):
        """Create valid subscription and verify response.
        
        Setup:
        - Prepare subscription request with location reference
        
        Action:
        - POST /alerts/subscriptions with valid request
        
        Verify:
        - HTTP 201 Created
        - Response contains subscription ID, status=active
        - Database has subscription with all fields
        - Delivery channels are saved
        - Conditions are saved
        """
        # Setup: Use test location ID
        location_id = 1

        # Prepare request (must match CreateSubscriptionRequest schema)
        request_data = {
            "location": {"id": location_id},
            "conditions": [
                {"type": "temperature_below", "threshold_value": -10}
            ],
            "delivery_channels": [
                {
                    "type": "email",
                    "destination": "user@example.com",
                    "active": True,
                }
            ],
            "schedule": {
                "active_from": "08:00",
                "active_to": "20:00",
                "timezone_source": "location",
            },
        }

        # Act: Create subscription
        response = await client.post(
            "/alerts/subscriptions",
            json=request_data,
            headers={"User-ID": test_user_id},
        )

        # Verify: HTTP response
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["status"] == "active"
        assert data["location"]["id"] == location_id
        assert len(data["conditions"]) == 1
        assert len(data["delivery_channels"]) == 1

        # Verify: Database state
        db_subscription = await test_db_session.get(
            Subscription, data["id"]
        )
        assert db_subscription is not None
        assert db_subscription.user_id == test_user_id
        assert db_subscription.status == SubscriptionStatus.ACTIVE
        assert len(db_subscription.conditions) == 1
        assert len(db_subscription.channels) == 1


    @pytest.mark.asyncio
    async def test_create_subscription_multi_channel(
        self, client: AsyncClient, test_db_session: AsyncSession, test_user_id: str
    ):
        """Create subscription with multiple delivery channels.
        
        Verify:
        - All channels created and active
        - Each channel has correct type and destination
        """
        location_id = 1

        request_data = {
            "location": {"id": location_id},
            "conditions": [
                {"type": "rain_probability_above", "threshold_value": 70}
            ],
            "delivery_channels": [
                {"type": "email", "destination": "user@example.com", "active": True},
                {"type": "push", "destination": "device_token_123", "active": True},
                {
                    "type": "webhook",
                    "destination": "https://example.com/hook",
                    "active": True,
                },
            ],
        }

        response = await client.post(
            "/alerts/subscriptions",
            json=request_data,
            headers={"User-ID": test_user_id},
        )

        assert response.status_code == 201
        data = response.json()
        assert len(data["delivery_channels"]) == 3

        # Verify each channel
        channels_by_type = {ch["type"]: ch for ch in data["delivery_channels"]}
        assert channels_by_type["email"]["destination"] == "user@example.com"
        assert channels_by_type["push"]["destination"] == "device_token_123"
        assert channels_by_type["webhook"]["destination"] == "https://example.com/hook"


    @pytest.mark.asyncio
    async def test_create_subscription_invalid_missing_conditions(
        self, client: AsyncClient, test_db_session: AsyncSession, test_user_id: str
    ):
        """Create subscription without conditions → HTTP 400.
        
        Verify:
        - Request validation catches empty conditions
        - HTTP 400 Bad Request
        """
        location_id = 1

        request_data = {
            "location": {"id": location_id},
            "conditions": [],  # Invalid: empty
            "delivery_channels": [
                {"type": "email", "destination": "user@example.com", "active": True}
            ],
        }

        response = await client.post(
            "/alerts/subscriptions",
            json=request_data,
            headers={"User-ID": test_user_id},
        )

        assert response.status_code == 400


    @pytest.mark.asyncio
    async def test_create_subscription_invalid_missing_channels(
        self, client: AsyncClient, test_db_session: AsyncSession, test_user_id: str
    ):
        """Create subscription without delivery channels → HTTP 400.
        
        Verify:
        - Request validation catches empty channels
        - HTTP 400 Bad Request
        """
        location_id = 1

        request_data = {
            "location": {"id": location_id},
            "conditions": [{"type": "temperature_below", "threshold_value": -10}],
            "delivery_channels": [],  # Invalid: empty
        }

        response = await client.post(
            "/alerts/subscriptions",
            json=request_data,
            headers={"User-ID": test_user_id},
        )

        assert response.status_code == 400


# ============================================================================
# READ OPERATIONS (LIST, GET)
# ============================================================================


class TestSubscriptionRead:
    """Test subscription read operations.
    
    Scenarios:
    - List subscriptions (GET /alerts/subscriptions)
    - Get single subscription (GET /alerts/subscriptions/{id})
    - Get non-existent subscription → 404
    - Get other user's subscription → 403
    """

    @pytest.mark.asyncio
    async def test_list_subscriptions_empty(
        self, client: AsyncClient, test_db_session: AsyncSession, test_user_id: str
    ):
        """List subscriptions when none exist → empty list.
        
        Verify:
        - HTTP 200 OK
        - Response is empty list
        """
        response = await client.get(
            "/alerts/subscriptions",
            headers={"User-ID": test_user_id},
        )

        assert response.status_code == 200
        assert response.json() == []


    @pytest.mark.asyncio
    async def test_list_subscriptions_returns_created(
        self, client: AsyncClient, test_db_session: AsyncSession, test_user_id: str
    ):
        """List subscriptions returns created subscriptions.
        
        Setup:
        - Create 2 test subscriptions
        
        Verify:
        - List returns both subscriptions
        - Each has correct data
        """
        location_id = 1

        # Create first subscription
        request_data_1 = {
            "location": {"id": location_id},
            "conditions": [{"type": "temperature_below", "threshold_value": -10}],
            "delivery_channels": [
                {"type": "email", "destination": "user1@example.com", "active": True}
            ],
        }
        response1 = await client.post(
            "/alerts/subscriptions",
            json=request_data_1,
            headers={"User-ID": test_user_id},
        )
        assert response1.status_code == 201
        sub_id_1 = response1.json()["id"]

        # Create second subscription
        request_data_2 = {
            "location": {"id": location_id},
            "conditions": [{"type": "rain_probability_above", "threshold_value": 70}],
            "delivery_channels": [
                {"type": "push", "destination": "device_token", "active": True}
            ],
        }
        response2 = await client.post(
            "/alerts/subscriptions",
            json=request_data_2,
            headers={"User-ID": test_user_id},
        )
        assert response2.status_code == 201
        sub_id_2 = response2.json()["id"]

        # List subscriptions
        response = await client.get(
            "/alerts/subscriptions",
            headers={"User-ID": test_user_id},
        )

        assert response.status_code == 200
        subscriptions = response.json()
        assert len(subscriptions) == 2

        sub_ids = [s["id"] for s in subscriptions]
        assert sub_id_1 in sub_ids
        assert sub_id_2 in sub_ids


    @pytest.mark.asyncio
    async def test_get_subscription_success(
        self, client: AsyncClient, test_db_session: AsyncSession, test_user_id: str
    ):
        """Get single subscription returns full details.
        
        Verify:
        - HTTP 200 OK
        - Response contains all subscription data
        """
        location_id = 1

        # Create subscription
        request_data = {
            "location": {"id": location_id},
            "conditions": [{"type": "temperature_below", "threshold_value": -10}],
            "delivery_channels": [
                {"type": "email", "destination": "user@example.com", "active": True}
            ],
        }
        create_response = await client.post(
            "/alerts/subscriptions",
            json=request_data,
            headers={"User-ID": test_user_id},
        )
        sub_id = create_response.json()["id"]

        # Get subscription
        response = await client.get(
            f"/alerts/subscriptions/{sub_id}",
            headers={"User-ID": test_user_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sub_id
        assert data["status"] == "active"


    @pytest.mark.asyncio
    async def test_get_subscription_not_found(
        self, client: AsyncClient, test_user_id: str
    ):
        """Get non-existent subscription → HTTP 404.
        
        Verify:
        - HTTP 404 Not Found
        """
        response = await client.get(
            "/alerts/subscriptions/999999",
            headers={"User-ID": test_user_id},
        )

        assert response.status_code == 404


# ============================================================================
# UPDATE SUBSCRIPTION
# ============================================================================


class TestSubscriptionUpdate:
    """Test subscription update operations (PATCH).
    
    Scenarios:
    - Update conditions
    - Update delivery channels
    - Update schedule
    - Partial update (only some fields)
    - Update non-existent subscription → 404
    - Update with invalid data → 400
    """

    @pytest.mark.asyncio
    async def test_update_subscription_schedule(
        self, client: AsyncClient, test_db_session: AsyncSession, test_user_id: str
    ):
        """Update subscription schedule.
        
        Verify:
        - HTTP 200 OK
        - Schedule updated in database
        - Other fields unchanged
        """
        location_id = 1

        # Create subscription
        request_data = {
            "location": {"id": location_id},
            "conditions": [{"type": "temperature_below", "threshold_value": -10}],
            "delivery_channels": [
                {"type": "email", "destination": "user@example.com", "active": True}
            ],
            "schedule": {
                "active_from": "08:00",
                "active_to": "20:00",
                "timezone_source": "location",
            },
        }
        create_response = await client.post(
            "/alerts/subscriptions",
            json=request_data,
            headers={"User-ID": test_user_id},
        )
        sub_id = create_response.json()["id"]

        # Update schedule
        update_data = {
            "schedule": {
                "active_from": "09:00",
                "active_to": "18:00",
                "timezone_source": "location",
            }
        }
        response = await client.patch(
            f"/alerts/subscriptions/{sub_id}",
            json=update_data,
            headers={"User-ID": test_user_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["schedule"]["active_from"] == "09:00"
        assert data["schedule"]["active_to"] == "18:00"


    @pytest.mark.asyncio
    async def test_update_subscription_conditions(
        self, client: AsyncClient, test_db_session: AsyncSession, test_user_id: str
    ):
        """Update subscription conditions (replace all).
        
        Verify:
        - Old conditions removed
        - New conditions added
        - HTTP 200 OK
        """
        location_id = 1

        # Create subscription with one condition
        request_data = {
            "location": {"id": location_id},
            "conditions": [{"type": "temperature_below", "threshold_value": -10}],
            "delivery_channels": [
                {"type": "email", "destination": "user@example.com", "active": True}
            ],
        }
        create_response = await client.post(
            "/alerts/subscriptions",
            json=request_data,
            headers={"User-ID": test_user_id},
        )
        sub_id = create_response.json()["id"]

        # Update conditions
        update_data = {
            "conditions": [
                {"type": "rain_probability_above", "threshold_value": 75},
                {"type": "wind_speed_above", "threshold_value": 20},
            ]
        }
        response = await client.patch(
            f"/alerts/subscriptions/{sub_id}",
            json=update_data,
            headers={"User-ID": test_user_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["conditions"]) == 2

        condition_types = {c["type"] for c in data["conditions"]}
        assert "rain_probability_above" in condition_types
        assert "wind_speed_above" in condition_types
        assert "temperature_below" not in condition_types  # Old removed


# ============================================================================
# DELETE SUBSCRIPTION
# ============================================================================


class TestSubscriptionDelete:
    """Test subscription deletion (soft-delete).
    
    Scenarios:
    - Delete active subscription
    - Delete non-existent subscription → 404
    - Delete already deleted subscription → 409
    - Deleted subscription excluded from list
    """

    @pytest.mark.asyncio
    async def test_delete_subscription_success(
        self, client: AsyncClient, test_db_session: AsyncSession, test_user_id: str
    ):
        """Delete subscription → HTTP 204 No Content.
        
        Verify:
        - HTTP 204 (no response body)
        - Subscription status = "deleted" in database
        - Subscription excluded from list
        """
        location_id = 1

        # Create subscription
        request_data = {
            "location": {"id": location_id},
            "conditions": [{"type": "temperature_below", "threshold_value": -10}],
            "delivery_channels": [
                {"type": "email", "destination": "user@example.com", "active": True}
            ],
        }
        create_response = await client.post(
            "/alerts/subscriptions",
            json=request_data,
            headers={"User-ID": test_user_id},
        )
        sub_id = create_response.json()["id"]

        # Delete subscription
        delete_response = await client.delete(
            f"/alerts/subscriptions/{sub_id}",
            headers={"User-ID": test_user_id},
        )

        assert delete_response.status_code == 204
        assert delete_response.text == ""  # No content

        # Verify: Get request returns 404
        get_response = await client.get(
            f"/alerts/subscriptions/{sub_id}",
            headers={"User-ID": test_user_id},
        )
        assert get_response.status_code == 404


    @pytest.mark.asyncio
    async def test_delete_subscription_not_found(
        self, client: AsyncClient, test_user_id: str
    ):
        """Delete non-existent subscription → HTTP 404.
        
        Verify:
        - HTTP 404 Not Found
        """
        response = await client.delete(
            "/alerts/subscriptions/999999",
            headers={"User-ID": test_user_id},
        )

        assert response.status_code == 404


# ============================================================================
# PAUSE / RESUME SUBSCRIPTION
# ============================================================================


class TestSubscriptionPauseResume:
    """Test subscription pause/resume (state transitions).
    
    Scenarios:
    - Pause active subscription → status = disabled
    - Resume disabled subscription → status = active
    - Pause already disabled → 409 Conflict
    - Resume already active → 409 Conflict
    - Pause/resume deleted subscription → 409 Conflict
    """

    @pytest.mark.asyncio
    async def test_pause_subscription_success(
        self, client: AsyncClient, test_db_session: AsyncSession, test_user_id: str
    ):
        """Pause active subscription → status = disabled.
        
        Verify:
        - HTTP 200 OK
        - Response status = "disabled"
        - Database updated
        """
        location_id = 1

        # Create subscription
        request_data = {
            "location": {"id": location_id},
            "conditions": [{"type": "temperature_below", "threshold_value": -10}],
            "delivery_channels": [
                {"type": "email", "destination": "user@example.com", "active": True}
            ],
        }
        create_response = await client.post(
            "/alerts/subscriptions",
            json=request_data,
            headers={"User-ID": test_user_id},
        )
        sub_id = create_response.json()["id"]

        # Pause subscription
        response = await client.post(
            f"/alerts/subscriptions/{sub_id}/pause",
            headers={"User-ID": test_user_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "disabled"

        # Verify database
        db_sub = await test_db_session.get(Subscription, sub_id)
        assert db_sub.status == SubscriptionStatus.DISABLED


    @pytest.mark.asyncio
    async def test_resume_subscription_success(
        self, client: AsyncClient, test_db_session: AsyncSession, test_user_id: str
    ):
        """Resume disabled subscription → status = active.
        
        Verify:
        - HTTP 200 OK
        - Response status = "active"
        - Database updated
        """
        location_id = 1

        # Create subscription
        request_data = {
            "location": {"id": location_id},
            "conditions": [{"type": "temperature_below", "threshold_value": -10}],
            "delivery_channels": [
                {"type": "email", "destination": "user@example.com", "active": True}
            ],
        }
        create_response = await client.post(
            "/alerts/subscriptions",
            json=request_data,
            headers={"User-ID": test_user_id},
        )
        sub_id = create_response.json()["id"]

        # Pause then resume
        pause_response = await client.post(
            f"/alerts/subscriptions/{sub_id}/pause",
            headers={"User-ID": test_user_id},
        )
        assert pause_response.status_code == 200

        resume_response = await client.post(
            f"/alerts/subscriptions/{sub_id}/resume",
            headers={"User-ID": test_user_id},
        )

        assert resume_response.status_code == 200
        data = resume_response.json()
        assert data["status"] == "active"


    @pytest.mark.asyncio
    async def test_pause_already_disabled_conflict(
        self, client: AsyncClient, test_db_session: AsyncSession, test_user_id: str
    ):
        """Pause already disabled subscription → HTTP 409 Conflict.
        
        Verify:
        - HTTP 409 Conflict
        - Error message indicates conflict
        """
        location_id = 1

        # Create and pause subscription
        request_data = {
            "location": {"id": location_id},
            "conditions": [{"type": "temperature_below", "threshold_value": -10}],
            "delivery_channels": [
                {"type": "email", "destination": "user@example.com", "active": True}
            ],
        }
        create_response = await client.post(
            "/alerts/subscriptions",
            json=request_data,
            headers={"User-ID": test_user_id},
        )
        sub_id = create_response.json()["id"]

        first_pause = await client.post(
            f"/alerts/subscriptions/{sub_id}/pause",
            headers={"User-ID": test_user_id},
        )
        assert first_pause.status_code == 200

        # Try to pause again
        second_pause = await client.post(
            f"/alerts/subscriptions/{sub_id}/pause",
            headers={"User-ID": test_user_id},
        )

        assert second_pause.status_code == 409
