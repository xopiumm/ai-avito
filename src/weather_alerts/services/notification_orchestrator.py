"""Notification Orchestration Service for Weather Alerts.

This is the main orchestration layer that coordinates the workflow:
1. Receive weather forecast/event
2. Find subscriptions matching the location
3. Evaluate weather conditions against each subscription
4. Check delivery schedule (local time window)
5. Check deduplication (prevent duplicates within 12h window per channel)
6. Prepare notifications for delivery or pending

Orchestration flow with deduplication (T020 integration):
- Condition matching uses ConditionEvaluationService (T014)
- Schedule checking uses ScheduleService (T015)
- Deduplication checking uses DeduplicationService (T020)
- Results are prepared for Delivery Service (to be implemented)
- Pending notifications are prepared for Pending Manager (to be implemented)

Deduplication integration (T021):
- Dedup gate is placed BEFORE sending (see _prepare_notifications_for_sending)
- Each channel is checked independently for duplicates
- Dedup window: 12 hours per (user, subscription, channel, event_type)
- First occurrence → send, marked in Redis
- Duplicate within 12h → skip, no send
- After 12h → can send again (TTL expires)

This service is testable and extensible:
- Pure business logic (no I/O except data dependencies)
- Clear separation of steps
- Prepared for future additions (retries, delivery)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Tuple
from enum import Enum as PyEnum

from src.weather_alerts.adapters.weather_provider import Forecast
from src.weather_alerts.domain.models.subscription import (
    Subscription,
    DeliveryChannel,
    SubscriptionStatus,
)
from src.weather_alerts.services.condition_evaluation_service import (
    ConditionEvaluationService,
    ConditionEvaluationResult,
    EventType,
)
from src.weather_alerts.services.schedule_service import (
    ScheduleService,
    ScheduleCheckResult,
    ScheduleStatus,
)
from src.weather_alerts.services.deduplication_service import (
    DeduplicationService,
    DuplicationStatus,
)


# ============================================================================
# RESULT MODELS - ORCHESTRATION OUTPUT
# ============================================================================


class NotificationState(str, PyEnum):
    """State of prepared notification."""
    
    READY_TO_SEND = "ready_to_send"  # Delivery window open, can send now
    PENDING_SCHEDULED = "pending_scheduled"  # Waiting for delivery window to open
    SKIPPED_NO_MATCH = "skipped_no_match"  # Conditions not met
    SKIPPED_INACTIVE_SUBSCRIPTION = "skipped_inactive_subscription"  # Subscription disabled/deleted


@dataclass
class PreparedNotification:
    """Notification prepared for delivery through a specific channel.
    
    Represents a single notification ready to be delivered via one channel.
    One evaluation result can produce multiple PreparedNotifications
    (one per active delivery channel).
    
    Attributes:
        subscription_id: Which subscription triggered this notification
        user_id: User who owns the subscription
        location_id: Location of the subscription
        delivery_channel_id: Which channel to deliver through
        delivery_channel_type: Type (email, push, webhook) for routing
        destination: Address/endpoint (email, device token, webhook URL)
        event_type: EventType from condition evaluation (for templating)
        matched_conditions: List of conditions that matched (for context)
        notification_body: Message content (filled by delivery service)
        send_at_utc: When to actually send (should be ASAP, typically now)
        source_forecast_timestamp: When the forecast was from (for dedup window later)
    """
    
    subscription_id: int
    user_id: str
    location_id: int
    delivery_channel_id: int
    delivery_channel_type: str
    destination: str
    event_type: EventType
    matched_conditions_count: int
    send_at_utc: datetime
    source_forecast_timestamp: datetime  # From forecast.current.timestamp


@dataclass
class PendingNotificationRequest:
    """Request to save a notification for later delivery.
    
    When delivery window is closed (schedule check fails),
    notification is saved as pending to be delivered when window opens.
    
    Attributes:
        subscription_id: Which subscription
        location_id: Which location
        event_type: Primary event type (for templating)
        matched_conditions_count: How many conditions matched
        window_opens_at_utc: When delivery window opens (from schedule service)
        window_closes_at_utc: When delivery window closes
        source_forecast_timestamp: Forecast timestamp (for future dedup)
    """
    
    subscription_id: int
    location_id: int
    event_type: EventType
    matched_conditions_count: int
    window_opens_at_utc: datetime
    window_closes_at_utc: datetime
    source_forecast_timestamp: datetime  # For future dedup window check


@dataclass
class OrchestrationMetrics:
    """Metrics from orchestration run."""
    
    timestamp_utc: datetime
    subscriptions_evaluated: int
    subscriptions_matched: int
    subscriptions_allowed: int
    subscriptions_pending: int
    subscriptions_skipped: int
    total_notifications_prepared: int  # All channels, all subs


@dataclass
class OrchestrationResult:
    """Result of orchestrating notifications for a weather event.
    
    Contains all notifications ready to be sent now, all notifications
    waiting for schedule windows to open, and metrics.
    
    Attributes:
        location_id: Which location this event is for
        event_timestamp_utc: When the event was detected
        prepared_notifications: List of notifications ready to send now
        pending_requests: List of pending notification requests
        metrics: Statistics about the run
        execution_time_ms: How long orchestration took (for performance monitoring)
    """
    
    location_id: int
    event_timestamp_utc: datetime
    prepared_notifications: List[PreparedNotification] = field(default_factory=list)
    pending_requests: List[PendingNotificationRequest] = field(default_factory=list)
    metrics: OrchestrationMetrics = field(default_factory=lambda: OrchestrationMetrics(
        timestamp_utc=datetime.now(timezone.utc),
        subscriptions_evaluated=0,
        subscriptions_matched=0,
        subscriptions_allowed=0,
        subscriptions_pending=0,
        subscriptions_skipped=0,
        total_notifications_prepared=0,
    ))
    execution_time_ms: int = 0


# ============================================================================
# ORCHESTRATION SERVICE
# ============================================================================


class NotificationOrchestrator:
    """Orchestrates the notification workflow.
    
    Responsibilities:
    1. Receive weather event (forecast) for a location
    2. Find all active subscriptions for that location
    3. Evaluate conditions using ConditionEvaluationService
    4. Check schedule using ScheduleService
    5. Prepare notifications for delivery or pending
    
    This service is:
    - Extensible: designed to integrate with future dedup/retry services
    - Testable: pure business logic, no I/O except dependencies
    - Performant: targets <1 min from event to first delivery attempt (NFR-001)
    
    Usage:
        orchestrator = NotificationOrchestrator(
            condition_service=ConditionEvaluationService(),
            schedule_service=ScheduleService(),
        )
        result = orchestrator.orchestrate_notifications(
            location_id=location.id,
            subscriptions=[...],  # from DB
            forecast=forecast,  # from weather provider
        )
        
        # Send immediately
        for notification in result.prepared_notifications:
            await delivery_service.send(notification)
        
        # Schedule for later
        for pending in result.pending_requests:
            await pending_manager.save(pending)
    """
    
    def __init__(
        self,
        condition_service: Optional[ConditionEvaluationService] = None,
        schedule_service: Optional[ScheduleService] = None,
        deduplication_service: Optional[DeduplicationService] = None,
    ):
        """Initialize orchestrator with required services.
        
        Args:
            condition_service: Service for evaluating weather conditions
            schedule_service: Service for checking delivery schedules
            deduplication_service: Service for deduplication (T020)
        """
        self.condition_service = condition_service or ConditionEvaluationService()
        self.schedule_service = schedule_service or ScheduleService()
        self.deduplication_service = deduplication_service or DeduplicationService()
    
    async def orchestrate_notifications(
        self,
        location_id: int,
        subscriptions: List[Subscription],
        forecast: Forecast,
        evaluation_time_utc: Optional[datetime] = None,
    ) -> OrchestrationResult:
        """Orchestrate notifications for a weather event at a location.
        
        Main orchestration entrypoint: coordinates the full workflow from
        weather event to prepared notifications/pending.
        
        Args:
            location_id: Location ID for the weather event
            subscriptions: List of subscriptions for this location
            forecast: Weather forecast data
            evaluation_time_utc: When to evaluate (default: now)
        
        Returns:
            OrchestrationResult with prepared notifications and pending requests
        
        Notes:
            - Only evaluates ACTIVE subscriptions
            - Each subscription produces 0+ prepared notifications
            - Each channel is a separate notification
            - Deduplication is checked per channel (T021)
            - Performance targets <1 min (NFR-001)
        """
        if evaluation_time_utc is None:
            evaluation_time_utc = datetime.now(timezone.utc)
        
        start_time = datetime.now(timezone.utc)
        
        # Initialize result
        result = OrchestrationResult(
            location_id=location_id,
            event_timestamp_utc=evaluation_time_utc,
        )
        
        # Step 1: Filter ACTIVE subscriptions only
        active_subscriptions = self._filter_active_subscriptions(subscriptions)
        result.metrics.subscriptions_evaluated = len(active_subscriptions)
        
        # Step 2: Process each subscription (now async for dedup checks)
        for subscription in active_subscriptions:
            await self._process_subscription(
                subscription=subscription,
                forecast=forecast,
                evaluation_time_utc=evaluation_time_utc,
                result=result,
            )
        
        # Calculate metrics
        result.metrics.total_notifications_prepared = len(result.prepared_notifications)
        
        # Calculate execution time
        end_time = datetime.now(timezone.utc)
        delta = end_time - start_time
        result.execution_time_ms = int(delta.total_seconds() * 1000)
        
        return result
    
    def _filter_active_subscriptions(
        self,
        subscriptions: List[Subscription],
    ) -> List[Subscription]:
        """Filter subscriptions to only ACTIVE ones.
        
        Skips:
        - DISABLED subscriptions (user paused them)
        - DELETED subscriptions (soft-deleted)
        """
        active = [
            sub for sub in subscriptions
            if sub.status == SubscriptionStatus.ACTIVE
        ]
        return active
    
    async def _process_subscription(
        self,
        subscription: Subscription,
        forecast: Forecast,
        evaluation_time_utc: datetime,
        result: OrchestrationResult,
    ) -> None:
        """Process a single subscription through the full workflow.
        
        Steps:
        1. Evaluate weather conditions
        2. If conditions match:
           a. Check delivery schedule
           b. If allowed → check deduplication, then prepare for sending (T021)
           c. If blocked → prepare for pending
        3. If conditions don't match → skip
        """
        # Step 1: Evaluate conditions
        try:
            condition_result = self.condition_service.evaluate_subscription(
                subscription_id=subscription.id,
                conditions=subscription.conditions,
                forecast=forecast,
            )
        except Exception as e:
            # TODO: Handle gracefully, maybe log and skip
            return
        
        # Step 2: Check if conditions matched
        if not condition_result.matched:
            result.metrics.subscriptions_skipped += 1
            return  # No match, skip this subscription
        
        result.metrics.subscriptions_matched += 1
        
        # Step 3: Check delivery schedule
        try:
            schedule_result = self.schedule_service.check_schedule(
                subscription=subscription,
                check_time_utc=evaluation_time_utc,
            )
        except Exception as e:
            # TODO: Handle gracefully (invalid schedule, missing timezone)
            return
        
        # Step 4: Process based on schedule status
        if schedule_result.is_allowed:
            result.metrics.subscriptions_allowed += 1
            # T021: Dedup check happens in _prepare_notifications_for_sending
            await self._prepare_notifications_for_sending(
                subscription=subscription,
                condition_result=condition_result,
                send_at_utc=evaluation_time_utc,
                result=result,
            )
        else:
            result.metrics.subscriptions_pending += 1
            self._prepare_notifications_for_pending(
                subscription=subscription,
                condition_result=condition_result,
                schedule_result=schedule_result,
                forecast=forecast,
                result=result,
            )
    
    async def _prepare_notifications_for_sending(
        self,
        subscription: Subscription,
        condition_result: ConditionEvaluationResult,
        send_at_utc: datetime,
        result: OrchestrationResult,
    ) -> None:
        """Prepare notifications to send immediately (window is open).
        
        T021 INTEGRATION: Deduplication gate happens here
        
        Creates one PreparedNotification per active delivery channel,
        but only if it's not a duplicate (dedup check per channel).
        
        Deduplication flow:
        1. Get list of active channels
        2. For each channel:
           a. Call dedup_service.is_duplicate_and_mark()
              - Checks if this (user, subscription, channel, event_type) was seen in last 12h
              - Atomically marks it in Redis with 12h TTL if new
              - Returns status: FIRST_OCCURRENCE, DUPLICATE, or CHECK_FAILED
           b. FIRST_OCCURRENCE → proceed to create PreparedNotification
           c. DUPLICATE → skip (already notified in last 12h)
           d. CHECK_FAILED → proceed anyway (conservative: don't block on Redis errors)
        3. Only PreparedNotifications for passing channels are added to result
        """
        # Get active delivery channels
        active_channels = self._filter_active_channels(subscription.channels)
        
        if not active_channels:
            # Subscription has no active channels, skip
            return
        
        # Create one notification per channel, but check dedup first
        for channel in active_channels:
            # T021: DEDUP GATE - Check deduplication per channel
            try:
                dedup_result = await self.deduplication_service.is_duplicate_and_mark(
                    user_id=subscription.user_id,
                    subscription_id=subscription.id,
                    channel=channel.type,  # email, push, webhook
                    event_type=str(condition_result.event_type),
                )
            except Exception as e:
                # Redis error during dedup check
                # Conservative: log and proceed (don't block delivery)
                dedup_result = None
            
            # Determine if we should send this notification
            should_send = True
            if dedup_result:
                if dedup_result.status == DuplicationStatus.DUPLICATE:
                    # Skip: already notified within 12h
                    should_send = False
                elif dedup_result.status == DuplicationStatus.CHECK_FAILED:
                    # Conservative: proceed anyway
                    should_send = True
                # FIRST_OCCURRENCE: should_send = True (already set above)
            
            if not should_send:
                # Skip this channel (deduplicated)
                continue
            
            # Create notification for this channel
            notification = PreparedNotification(
                subscription_id=subscription.id,
                user_id=subscription.user_id,
                location_id=subscription.location_id,
                delivery_channel_id=channel.id,
                delivery_channel_type=channel.type,
                destination=channel.destination,
                event_type=condition_result.event_type,
                matched_conditions_count=len(condition_result.matched_conditions),
                send_at_utc=send_at_utc,
                source_forecast_timestamp=condition_result.weather_data_timestamp,
            )
            result.prepared_notifications.append(notification)
    
    def _prepare_notifications_for_pending(
        self,
        subscription: Subscription,
        condition_result: ConditionEvaluationResult,
        schedule_result: ScheduleCheckResult,
        forecast: Forecast,
        result: OrchestrationResult,
    ) -> None:
        """Prepare pending notification request (window is closed, wait for next opening).
        
        Creates ONE PendingNotificationRequest per subscription
        (multiple channels will be handled by pending manager when it's time to send).
        """
        # Calculate window closing time
        next_window_utc = schedule_result.next_allowed_time_utc
        
        if not next_window_utc:
            # Should not happen, but be defensive
            return
        
        # Estimate window close time (end of delivery window)
        # TODO: This could be more sophisticated, potentially from ScheduleService
        # For now, assume standard assumptions
        if schedule_result.active_to_local:
            # Calculate when window closes based on active_to time
            # For pending manager to know when to stop waiting
            # This is approximate - real closing time should come from ScheduleService
            window_close_utc = self._estimate_window_close_time(
                active_to_local=schedule_result.active_to_local,
                next_open_utc=next_window_utc,
            )
        else:
            window_close_utc = next_window_utc  # Fallback
        
        pending_request = PendingNotificationRequest(
            subscription_id=subscription.id,
            location_id=subscription.location_id,
            event_type=condition_result.event_type,
            matched_conditions_count=len(condition_result.matched_conditions),
            window_opens_at_utc=next_window_utc,
            window_closes_at_utc=window_close_utc,
            source_forecast_timestamp=condition_result.weather_data_timestamp,
        )
        result.pending_requests.append(pending_request)
    
    def _filter_active_channels(
        self,
        channels: List[DeliveryChannel],
    ) -> List[DeliveryChannel]:
        """Filter delivery channels to only ACTIVE ones."""
        active = [ch for ch in channels if ch.active]
        return active
    
    def _estimate_window_close_time(
        self,
        active_to_local,
        next_open_utc: datetime,
    ) -> datetime:
        """Estimate when delivery window closes.
        
        Given:
        - active_to_local: e.g., time(20, 0) (20:00)
        - next_open_utc: When window opens (e.g., 2026-04-10 05:00 UTC)
        
        Calculate when window closes on the same day.
        
        This is an approximation - ideally would use ScheduleService
        for more sophisticated logic.
        """
        import pytz
        from datetime import time, timedelta
        
        # Get timezone from the open time (we need it to calc closing time)
        # For now, this assumes the subscription has a location with timezone
        # which should always be true
        tz = pytz.timezone("UTC")  # Placeholder - in real code would get from subscription
        
        # Convert next_open_utc to local in that timezone
        next_open_local = next_open_utc.astimezone(tz)
        
        # Replace time with active_to_local
        window_close_local = next_open_local.replace(
            hour=active_to_local.hour,
            minute=active_to_local.minute,
            second=0,
            microsecond=0,
        )
        
        # Convert back to UTC
        window_close_utc = window_close_local.astimezone(timezone.utc)
        
        return window_close_utc


# ============================================================================
# ORCHESTRATION EXCEPTIONS
# ============================================================================


class OrchestrationException(Exception):
    """Base exception for orchestration errors."""
    pass


class InvalidForecastData(OrchestrationException):
    """Forecast data is invalid or incomplete."""
    pass


class NoSubscriptionsFound(OrchestrationException):
    """No subscriptions found for the location."""
    pass


class OrchestrationError(OrchestrationException):
    """Unexpected error during orchestration."""
    pass
