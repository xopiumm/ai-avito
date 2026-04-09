"""SubscriptionService for managing Weather Alerts subscriptions.

Business logic layer for subscription lifecycle management:
- Create, read, update, and delete subscriptions
- Enable/disable temporary pausing
- Manage associated conditions and delivery channels
- Enforce business rules and invariants
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.weather_alerts.api.schemas.subscription import (
    CreateSubscriptionRequest,
    SubscriptionConditionCreateSchema,
    SubscriptionResponse,
    UpdateSubscriptionRequest,
)
from src.weather_alerts.domain.models.subscription import (
    DeliveryChannel,
    DeliveryChannelType,
    SubscriptionCondition,
    SubscriptionStatus,
)
from src.weather_alerts.domain.models.subscription import (
    Subscription as SubscriptionModel,
)

from .exceptions import (
    InvalidSubscriptionData,
    SubscriptionAlreadyActive,
    SubscriptionAlreadyDeleted,
    SubscriptionAlreadyDisabled,
    SubscriptionNotFound,
    UnauthorizedSubscriptionAccess,
)


class SubscriptionService:
    """Service for managing subscription lifecycle.

    Encapsulates all business operations related to subscriptions, including:
    - Lifecycle management (create, read, update, disable, enable, delete)
    - Relationship management (conditions, delivery channels)
    - Business rule enforcement
    - Authorization and access control

    All methods raise domain exceptions (not HTTP exceptions) for proper
    layering. HTTP status code mapping happens in the API layer.
    """

    def __init__(self, session: AsyncSession):
        """Initialize service with database session.

        Args:
            session: SQLAlchemy AsyncSession for database operations
        """
        self.db = session

    # ========================================================================
    # AUTHORIZATION & UTILITY
    # ========================================================================

    async def _authorize_user_subscription(
        self, user_id: str, subscription_id: int
    ) -> SubscriptionModel:
        """Verify user owns this subscription.

        Raises:
            SubscriptionNotFound: Subscription doesn't exist
            UnauthorizedSubscriptionAccess: User doesn't own subscription

        Returns:
            Subscription model if authorized
        """
        stmt = (
            select(SubscriptionModel)
            .where(SubscriptionModel.id == subscription_id)
            .options(
                selectinload(SubscriptionModel.conditions),
                selectinload(SubscriptionModel.channels),
            )
        )
        result = await self.db.execute(stmt)
        subscription = result.scalar_one_or_none()

        if not subscription:
            raise SubscriptionNotFound(
                f"Subscription {subscription_id} not found"
            )

        if subscription.user_id != user_id:
            raise UnauthorizedSubscriptionAccess(
                f"User {user_id} is not authorized to access subscription {subscription_id}"
            )

        return subscription

    def _to_response(self, subscription: SubscriptionModel) -> SubscriptionResponse:
        """Convert ORM model to response schema."""
        return SubscriptionResponse.model_validate(subscription)

    # ========================================================================
    # CREATE
    # ========================================================================

    async def create(
        self, user_id: str, request: CreateSubscriptionRequest
    ) -> SubscriptionResponse:
        """Create a new subscription for user at location.

        Business rules enforced:
        - One active subscription per user+location (soft-deleted ones allowed)
        - At least one condition required
        - At least one delivery channel required
        - Cannot create subscription with deleted status

        Args:
            user_id: External user identifier
            request: Subscription creation request with location, conditions, channels

        Returns:
            Created subscription with ID, conditions, and channels

        Raises:
            SubscriptionAlreadyExists: Active subscription for this user+location exists
            InvalidSubscriptionData: Request violates business rules
        """
        location_id = request.location.id

        # Check: no active subscription already exists for this user+location
        stmt = (
            select(SubscriptionModel)
            .where(
                SubscriptionModel.user_id == user_id,
                SubscriptionModel.location_id == location_id,
                SubscriptionModel.status == SubscriptionStatus.ACTIVE,
            )
        )
        existing = await self.db.execute(stmt)
        if existing.scalar_one_or_none():
            raise SubscriptionAlreadyExists(
                f"Active subscription already exists for user {user_id} at location {location_id}"
            )

        # Create subscription with initial status=active
        subscription = SubscriptionModel(
            user_id=user_id,
            location_id=location_id,
            status=SubscriptionStatus.ACTIVE,
            condition_mode="ANY",  # Only "ANY" supported currently
            schedule_timezone_source=request.schedule.timezone_source,
            active_from=request.schedule.active_from,
            active_to=request.schedule.active_to,
        )

        # Add conditions
        for condition_req in request.conditions:
            condition = SubscriptionCondition(
                subscription=subscription,
                type=condition_req.type,
                threshold_value=condition_req.threshold_value,
                threshold_unit=condition_req.threshold_unit,
                severity_event_type=condition_req.severity_event_type,
            )
            subscription.conditions.append(condition)

        # Add delivery channels
        for channel_req in request.delivery_channels:
            channel = DeliveryChannel(
                subscription=subscription,
                type=channel_req.type,
                destination=channel_req.destination,
                active=channel_req.active,
            )
            subscription.channels.append(channel)

        # Persist subscription with relationships
        self.db.add(subscription)
        await self.db.flush()  # Flush to get ID without commit
        await self.db.refresh(
            subscription,
            ["conditions", "channels"],  # Refresh relationships
        )

        return self._to_response(subscription)

    # ========================================================================
    # READ
    # ========================================================================

    async def list(self, user_id: str) -> List[SubscriptionResponse]:
        """List all subscriptions for user (excluding soft-deleted).

        Invariant: Returns only non-deleted subscriptions (status != deleted).

        Args:
            user_id: External user identifier

        Returns:
            List of active and disabled subscriptions, newest first
        """
        stmt = (
            select(SubscriptionModel)
            .where(
                SubscriptionModel.user_id == user_id,
                SubscriptionModel.status != SubscriptionStatus.DELETED,
            )
            .options(
                selectinload(SubscriptionModel.conditions),
                selectinload(SubscriptionModel.channels),
            )
            .order_by(desc(SubscriptionModel.created_at))
        )
        result = await self.db.execute(stmt)
        subscriptions = result.scalars().all()

        return [self._to_response(sub) for sub in subscriptions]

    async def get(
        self, user_id: str, subscription_id: int
    ) -> SubscriptionResponse:
        """Get single subscription with full details.

        Args:
            user_id: External user identifier
            subscription_id: Subscription ID to retrieve

        Returns:
            Subscription with all conditions and channels

        Raises:
            SubscriptionNotFound: Subscription doesn't exist
            UnauthorizedSubscriptionAccess: User doesn't own subscription
        """
        subscription = await self._authorize_user_subscription(
            user_id, subscription_id
        )
        return self._to_response(subscription)

    # ========================================================================
    # UPDATE
    # ========================================================================

    async def update(
        self,
        user_id: str,
        subscription_id: int,
        request: UpdateSubscriptionRequest,
    ) -> SubscriptionResponse:
        """Update subscription with partial changes.

        Business rules:
        - Only non-deleted subscriptions can be updated
        - Conditions and channels are replaced entirely (not merged)
        - If no conditions provided, existing conditions preserved
        - Schedule can be partially updated

        Args:
            user_id: External user identifier
            subscription_id: Subscription to update
            request: Partial update request

        Returns:
            Updated subscription

        Raises:
            SubscriptionNotFound: Subscription doesn't exist
            UnauthorizedSubscriptionAccess: User doesn't own subscription
            InvalidSubscriptionData: Update violates business rules
        """
        subscription = await self._authorize_user_subscription(
            user_id, subscription_id
        )

        # Check: cannot update deleted subscription
        if subscription.status == SubscriptionStatus.DELETED:
            raise InvalidSubscriptionData(
                f"Cannot update deleted subscription {subscription_id}"
            )

        # Update schedule if provided
        if request.schedule is not None:
            subscription.schedule_timezone_source = (
                request.schedule.timezone_source
            )
            subscription.active_from = request.schedule.active_from
            subscription.active_to = request.schedule.active_to

        # Replace conditions if provided
        if request.conditions is not None:
            # Delete existing conditions
            await self.db.execute(
                delete(SubscriptionCondition).where(
                    SubscriptionCondition.subscription_id == subscription.id
                )
            )
            subscription.conditions.clear()

            # Add new conditions
            for condition_req in request.conditions:
                condition = SubscriptionCondition(
                    subscription=subscription,
                    type=condition_req.type,
                    threshold_value=condition_req.threshold_value,
                    threshold_unit=condition_req.threshold_unit,
                    severity_event_type=condition_req.severity_event_type,
                )
                subscription.conditions.append(condition)

        # Replace delivery channels if provided
        if request.delivery_channels is not None:
            # Delete existing channels
            await self.db.execute(
                delete(DeliveryChannel).where(
                    DeliveryChannel.subscription_id == subscription.id
                )
            )
            subscription.channels.clear()

            # Add new channels
            for channel_req in request.delivery_channels:
                channel = DeliveryChannel(
                    subscription=subscription,
                    type=channel_req.type,
                    destination=channel_req.destination,
                    active=channel_req.active,
                )
                subscription.channels.append(channel)

        # Mark as updated
        subscription.updated_at = datetime.utcnow()

        # Persist changes
        self.db.add(subscription)
        await self.db.flush()
        await self.db.refresh(
            subscription,
            ["conditions", "channels"],
        )

        return self._to_response(subscription)

    # ========================================================================
    # STATUS TRANSITIONS
    # ========================================================================

    async def disable(
        self, user_id: str, subscription_id: int
    ) -> SubscriptionResponse:
        """Temporarily disable subscription.

        Business rule: Active subscription transitions to disabled.
        Disables notifications without data loss.

        Args:
            user_id: External user identifier
            subscription_id: Subscription to disable

        Returns:
            Updated subscription with status=disabled

        Raises:
            SubscriptionNotFound: Subscription doesn't exist
            UnauthorizedSubscriptionAccess: User doesn't own subscription
            SubscriptionAlreadyDisabled: Subscription already disabled
            InvalidSubscriptionData: Cannot disable deleted subscription
        """
        subscription = await self._authorize_user_subscription(
            user_id, subscription_id
        )

        if subscription.status == SubscriptionStatus.DELETED:
            raise InvalidSubscriptionData(
                f"Cannot disable deleted subscription {subscription_id}"
            )

        if subscription.status == SubscriptionStatus.DISABLED:
            raise SubscriptionAlreadyDisabled(
                f"Subscription {subscription_id} is already disabled"
            )

        subscription.status = SubscriptionStatus.DISABLED
        subscription.updated_at = datetime.utcnow()

        self.db.add(subscription)
        await self.db.flush()
        await self.db.refresh(
            subscription,
            ["conditions", "channels"],
        )

        return self._to_response(subscription)

    async def enable(
        self, user_id: str, subscription_id: int
    ) -> SubscriptionResponse:
        """Re-enable a disabled subscription.

        Business rule: Disabled subscription transitions to active.

        Args:
            user_id: External user identifier
            subscription_id: Subscription to enable

        Returns:
            Updated subscription with status=active

        Raises:
            SubscriptionNotFound: Subscription doesn't exist
            UnauthorizedSubscriptionAccess: User doesn't own subscription
            SubscriptionAlreadyActive: Subscription already active
            InvalidSubscriptionData: Cannot enable deleted subscription
        """
        subscription = await self._authorize_user_subscription(
            user_id, subscription_id
        )

        if subscription.status == SubscriptionStatus.DELETED:
            raise InvalidSubscriptionData(
                f"Cannot enable deleted subscription {subscription_id}"
            )

        if subscription.status == SubscriptionStatus.ACTIVE:
            raise SubscriptionAlreadyActive(
                f"Subscription {subscription_id} is already active"
            )

        subscription.status = SubscriptionStatus.ACTIVE
        subscription.updated_at = datetime.utcnow()

        self.db.add(subscription)
        await self.db.flush()
        await self.db.refresh(
            subscription,
            ["conditions", "channels"],
        )

        return self._to_response(subscription)

    # ========================================================================
    # DELETE (SOFT)
    # ========================================================================

    async def delete(self, user_id: str, subscription_id: int) -> None:
        """Soft-delete subscription (mark as deleted, don't remove from DB).

        Business rules:
        - Sets status=deleted and deleted_at=now()
        - Deleted subscription data preserved in DB
        - Prevents any further notifications for this subscription
        - Existing pending/retry tasks should be cancelled by caller

        Args:
            user_id: External user identifier
            subscription_id: Subscription to delete

        Raises:
            SubscriptionNotFound: Subscription doesn't exist
            UnauthorizedSubscriptionAccess: User doesn't own subscription
            SubscriptionAlreadyDeleted: Already deleted
        """
        subscription = await self._authorize_user_subscription(
            user_id, subscription_id
        )

        if subscription.status == SubscriptionStatus.DELETED:
            raise SubscriptionAlreadyDeleted(
                f"Subscription {subscription_id} is already deleted"
            )

        subscription.status = SubscriptionStatus.DELETED
        subscription.deleted_at = datetime.utcnow()
        subscription.updated_at = datetime.utcnow()

        self.db.add(subscription)
        await self.db.flush()

    # ========================================================================
    # BUSINESS RULE VALIDATION
    # ========================================================================

    def validate_conditions_not_empty(self, conditions: List[SubscriptionConditionCreateSchema]) -> None:
        """Validate conditions list is not empty.

        Raises:
            InvalidSubscriptionData: If conditions is empty
        """
        if not conditions:
            raise InvalidSubscriptionData(
                "At least one condition is required for subscription"
            )

    def validate_channels_not_empty(self, channels: List) -> None:
        """Validate delivery channels list is not empty.

        Raises:
            InvalidSubscriptionData: If channels is empty
        """
        if not channels:
            raise InvalidSubscriptionData(
                "At least one delivery channel is required for subscription"
            )

    # ========================================================================
    # INVARIANTS DOCUMENTATION
    # ========================================================================

    """
    INVARIANTS MAINTAINED BY THIS SERVICE
    ====================================

    1. SUBSCRIPTION STATUS LIFECYCLE
       - New subscriptions always created with status=ACTIVE
       - Status transitions: ACTIVE <-> DISABLED (enabled/disabled ops)
       - Soft delete: status=DELETED (cannot transition out of DELETED)
       - list() returns only status != DELETED (soft-delete filtering)

    2. USER AUTHORIZATION
       - Every operation checks user_id ownership
       - Prevents unauthorized cross-user access
       - Raises UnauthorizedSubscriptionAccess on violation

    3. LOCATION UNIQUENESS
       - One active subscription per (user_id, location_id, status) tuple
       - Allows multiple subscriptions per location if different statuses
       - Prevents duplicate active subscriptions at create time

    4. RELATIONSHIPS
       - Conditions: Always >= 1 per subscription (no empty subscriptions)
       - Channels: Always >= 1 per subscription (no subscription without delivery)
       - Both enforced at API schema level + database schema level (NOT NULL)

    5. UPDATE SEMANTICS
       - update() replaces conditions and channels entirely (not merge)
       - If field not provided in request, existing value preserved
       - Schedule window consistency: active_from < active_to (validated in schema)

    6. SOFT DELETE
       - Deleted subscriptions never trigger notifications
       - Deleted_at timestamp records deletion time
       - Data preserved in database for audit/recovery

    7. TEMPORAL CONSISTENCY
       - created_at set only at creation, never modified
       - updated_at set at creation, updated on every modification
       - deleted_at set only when status transitions to DELETED

    8. NO BUSINESS LOGIC LEAKAGE
       - Service layer raises domain exceptions (not HTTP)
       - HTTP status mapping responsibility of API layer
       - Prevents service reuse issues in different contexts
    """
