"""Schedule service for Weather Alerts.

This service handles delivery schedule validation and timezone-aware computations.
It checks whether current time falls within subscription's delivery window and
calculates the next allowed delivery time if needed (for pending notification flow).

Schedule logic:
- Active window (active_from, active_to) is interpreted in location's local timezone
- If active_from or active_to is None, delivery is allowed at any time
- Any time within [active_from, active_to] allows delivery
- Outside the window, notification goes to pending until next window opens

Timezone handling:
- All timestamps passed to service are UTC
- Service converts to location timezone for window comparison
- Returns results with UTC timestamps for orchestration
"""

from dataclasses import dataclass
from datetime import datetime, time, timezone, timedelta, date
from enum import Enum as PyEnum
from typing import Optional, Tuple
import pytz

from src.weather_alerts.domain.models.subscription import Subscription


# ============================================================================
# RESULT MODELS - TESTABLE INTERFACES
# ============================================================================


class ScheduleStatus(str, PyEnum):
    """Delivery schedule status."""
    
    ALLOWED = "allowed"          # Delivery allowed now
    PENDING_WINDOW_CLOSED = "pending_window_closed"  # Window closed, waiting for next opening
    NO_WINDOW = "no_window"      # No time restrictions, delivery allowed


@dataclass
class ScheduleCheckResult:
    """Result of checking whether delivery is allowed at a specific time.
    
    Attributes:
        subscription_id: ID of the subscription
        status: ScheduleStatus - is delivery allowed now?
        is_allowed: Convenience boolean (status == ALLOWED)
        current_time_local: Current time in location's timezone (for debugging)
        active_from_local: Window start in location's timezone
        active_to_local: Window end in location's timezone
        next_allowed_time_utc: When delivery will be allowed (if not allowed now)
        reason: Human-readable explanation (for logs)
    """
    
    subscription_id: int
    status: ScheduleStatus
    is_allowed: bool
    current_time_local: datetime  # With timezone info
    active_from_local: Optional[time]
    active_to_local: Optional[time]
    next_allowed_time_utc: Optional[datetime]  # UTC, for scheduling
    reason: str


@dataclass
class NextDeliveryWindow:
    """Information about the next allowed delivery time.
    
    Used for scheduling pending notifications to wake up at the right time.
    
    Attributes:
        window_opens_at_utc: When next delivery window opens (UTC)
        window_closes_at_utc: When next delivery window closes (UTC)
        in_minutes: Minutes until window opens
    """
    
    window_opens_at_utc: datetime  # UTC
    window_closes_at_utc: datetime  # UTC
    in_minutes: int


# ============================================================================
# VALIDATION EXCEPTIONS
# ============================================================================


class ScheduleValidationException(Exception):
    """Base exception for schedule validation errors."""
    pass


class InvalidScheduleFormat(ScheduleValidationException):
    """Schedule time format is invalid (not HH:MM)."""
    pass


class InvalidTimeWindow(ScheduleValidationException):
    """Time window configuration is invalid (start >= end)."""
    pass


class MissingTimezone(ScheduleValidationException):
    """Timezone information is missing."""
    pass


# ============================================================================
# SCHEDULE SERVICE
# ============================================================================


class ScheduleService:
    """Service for schedule and timezone-aware delivery window checking.
    
    Responsibilities:
    - Parse and validate HH:MM formatted schedule times
    - Convert UTC timestamps to location timezone
    - Check if delivery is allowed at current time
    - Calculate next allowed delivery time (for pending notifications)
    - Handle edge cases (no window, boundary times, timezone transitions)
    
    Usage:
        service = ScheduleService()
        result = service.check_schedule(
            subscription=subscription,
            check_time_utc=datetime.now(timezone.utc),
        )
        if result.is_allowed:
            # Send notification now
        else:
            # Schedule to send at result.next_allowed_time_utc
    """
    
    def check_schedule(
        self,
        subscription: Subscription,
        check_time_utc: datetime,
    ) -> ScheduleCheckResult:
        """Check if delivery is allowed at a specific time.
        
        Args:
            subscription: Subscription with active_from/active_to and location
            check_time_utc: Time to check (must be UTC with timezone info)
        
        Returns:
            ScheduleCheckResult with detailed status and next allowed time
        
        Raises:
            InvalidScheduleFormat: Schedule times are not HH:MM
            MissingTimezone: Location has no timezone
            InvalidTimeWindow: Start time >= end time
        """
        if not self._is_utc(check_time_utc):
            raise ValueError("check_time_utc must be in UTC timezone")
        
        # Validate location timezone
        if not subscription.location or not subscription.location.timezone:
            raise MissingTimezone(
                f"Subscription {subscription.id} location has no timezone"
            )
        
        # Get location timezone
        tz = pytz.timezone(subscription.location.timezone)
        
        # Convert check time to location's local time
        check_time_local = check_time_utc.astimezone(tz)
        current_time_hm = check_time_local.time()
        
        # Parse schedule windows (may be None if no restrictions)
        active_from = self._parse_time(subscription.active_from)
        active_to = self._parse_time(subscription.active_to)
        
        # Case 1: No window restrictions
        if active_from is None or active_to is None:
            return ScheduleCheckResult(
                subscription_id=subscription.id,
                status=ScheduleStatus.NO_WINDOW,
                is_allowed=True,
                current_time_local=check_time_local,
                active_from_local=active_from,
                active_to_local=active_to,
                next_allowed_time_utc=None,
                reason="No delivery window restrictions (always allowed)",
            )
        
        # Validate window (start < end)
        if active_from >= active_to:
            raise InvalidTimeWindow(
                f"Invalid schedule window: {active_from} >= {active_to}"
            )
        
        # Case 2: Within delivery window
        if active_from <= current_time_hm < active_to:
            return ScheduleCheckResult(
                subscription_id=subscription.id,
                status=ScheduleStatus.ALLOWED,
                is_allowed=True,
                current_time_local=check_time_local,
                active_from_local=active_from,
                active_to_local=active_to,
                next_allowed_time_utc=None,
                reason=f"Current time {current_time_hm} is within window "
                       f"[{active_from}, {active_to})",
            )
        
        # Case 3: Outside window - calculate next window
        next_window_utc = self._calculate_next_window_open(
            check_time_local=check_time_local,
            active_from=active_from,
            active_to=active_to,
            tz=tz,
        )
        
        return ScheduleCheckResult(
            subscription_id=subscription.id,
            status=ScheduleStatus.PENDING_WINDOW_CLOSED,
            is_allowed=False,
            current_time_local=check_time_local,
            active_from_local=active_from,
            active_to_local=active_to,
            next_allowed_time_utc=next_window_utc,
            reason=f"Current time {current_time_hm} is outside window "
                   f"[{active_from}, {active_to}); next window opens at "
                   f"{next_window_utc.isoformat()}",
        )
    
    def get_next_delivery_window(
        self,
        subscription: Subscription,
        current_time_utc: datetime,
    ) -> Optional[NextDeliveryWindow]:
        """Get information about the next allowed delivery window.
        
        Used for scheduling pending notifications to wake up at the right time.
        
        Args:
            subscription: Subscription with schedule
            current_time_utc: Current time (UTC) - used for computing next window time
        
        Returns:
            NextDeliveryWindow with opening/closing times, or None if no window
        
        Raises:
            Same as check_schedule()
        """
        result = self.check_schedule(subscription, current_time_utc)
        
        # If allowed now or no window, return None (no future window to schedule)
        if result.is_allowed or result.status == ScheduleStatus.NO_WINDOW:
            return None
        
        # Window is closed - calculate opening and closing times
        if not result.active_from_local or not result.active_to_local:
            return None  # Should not happen, but be defensive
        
        tz = pytz.timezone(subscription.location.timezone)
        next_open_utc = result.next_allowed_time_utc
        
        # Calculate closing time: same day at active_to
        # But we need to be careful: if next_open_utc is tomorrow (e.g., 08:00),
        # then closing time is same day (e.g., 20:00)
        next_open_local = next_open_utc.astimezone(tz)
        window_close_local = next_open_local.replace(
            hour=result.active_to_local.hour,
            minute=result.active_to_local.minute,
            second=0,
            microsecond=0,
        )
        window_close_utc = window_close_local.astimezone(timezone.utc)
        
        # Calculate minutes until window opens (from current_time_utc, not now)
        delta = next_open_utc - current_time_utc
        in_minutes = int(delta.total_seconds() / 60)
        
        return NextDeliveryWindow(
            window_opens_at_utc=next_open_utc,
            window_closes_at_utc=window_close_utc,
            in_minutes=in_minutes,
        )
    
    def _parse_time(self, time_str: Optional[str]) -> Optional[time]:
        """Parse HH:MM time string to time object.
        
        Args:
            time_str: Time in HH:MM format or None
        
        Returns:
            time object or None
        
        Raises:
            InvalidScheduleFormat: If format is invalid
        """
        if time_str is None:
            return None
        
        if not isinstance(time_str, str):
            raise InvalidScheduleFormat(f"Schedule time must be string, got {type(time_str)}")
        
        try:
            parts = time_str.split(":")
            if len(parts) != 2:
                raise ValueError("Invalid format")
            hour, minute = int(parts[0]), int(parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Hour or minute out of range")
            return time(hour, minute)
        except (ValueError, IndexError) as e:
            raise InvalidScheduleFormat(
                f"Schedule time must be HH:MM format, got '{time_str}': {e}"
            )
    
    def _calculate_next_window_open(
        self,
        check_time_local: datetime,
        active_from: time,
        active_to: time,
        tz: pytz.timezone,
    ) -> datetime:
        """Calculate when the next delivery window will open.
        
        Logic:
        - If current time is before active_from today, window opens today
        - If current time is after active_to today, window opens tomorrow
        
        Args:
            check_time_local: Current time in location's timezone
            active_from: Window start time
            active_to: Window end time
            tz: Location's timezone
        
        Returns:
            UTC datetime when next window opens
        """
        current_date = check_time_local.date()
        current_time = check_time_local.time()
        
        # Case 1: Current time is before window opens today
        # Window opens at active_from today
        if current_time < active_from:
            window_open_local = tz.localize(
                datetime.combine(current_date, active_from)
            )
            return window_open_local.astimezone(timezone.utc)
        
        # Case 2: Current time is after window closes
        # Window opens at active_from tomorrow
        next_day = current_date + timedelta(days=1)
        window_open_local = tz.localize(
            datetime.combine(next_day, active_from)
        )
        return window_open_local.astimezone(timezone.utc)
    
    @staticmethod
    def _is_utc(dt: datetime) -> bool:
        """Check if datetime object is in UTC timezone."""
        return dt.tzinfo is not None and dt.tzinfo == timezone.utc
