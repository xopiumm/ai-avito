"""Unit tests for ScheduleService.

Tests cover:
- Schedule window validation and parsing
- Timezone-aware delivery window checks
- All-day (no window) scenarios
- Boundary conditions (exactly at window start/end)
- Next delivery window calculation
- UTC/local time conversions
- Daylight saving time handling (pytz)
"""

from datetime import datetime, time, timezone, timedelta, date
from typing import Optional

import pytest
import pytz

from src.weather_alerts.domain.models.subscription import Subscription
from src.weather_alerts.services.schedule_service import (
    ScheduleService,
    ScheduleStatus,
    ScheduleCheckResult,
    InvalidScheduleFormat,
    InvalidTimeWindow,
    MissingTimezone,
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def schedule_service():
    """Create a schedule service instance."""
    return ScheduleService()


class MockLocation:
    """Mock Location with timezone."""
    
    def __init__(self, timezone_str: str = "Europe/Moscow"):
        self.id = 1
        self.timezone = timezone_str
        self.latitude = 55.75  # Moscow
        self.longitude = 37.62


@pytest.fixture
def moscow_location():
    """Moscow location (UTC+3)."""
    return MockLocation(timezone_str="Europe/Moscow")


@pytest.fixture
def tokyo_location():
    """Tokyo location (UTC+9)."""
    return MockLocation(timezone_str="Asia/Tokyo")


@pytest.fixture
def new_york_location():
    """New York location (UTC-5 or UTC-4 depending on DST)."""
    return MockLocation(timezone_str="America/New_York")


def create_mock_subscription(
    subscription_id: int = 1,
    active_from: Optional[str] = "08:00",
    active_to: Optional[str] = "20:00",
    location: Optional[MockLocation] = None,
) -> Subscription:
    """Helper to create mock subscription."""
    if location is None:
        location = MockLocation()
    
    subscription = Subscription(
        id=subscription_id,
        user_id="user1",
        location_id=location.id,
        status="active",
        condition_mode="ANY",
        schedule_timezone_source="location",
        active_from=active_from,
        active_to=active_to,
    )
    subscription.location = location
    return subscription


# ============================================================================
# TIMEZONE CONVERSION TESTS
# ============================================================================


def test_utc_to_local_conversion_moscow(schedule_service, moscow_location):
    """Test UTC to Moscow local time conversion."""
    # 2026-04-09 12:00:00 UTC = 2026-04-09 15:00:00 Moscow (UTC+3)
    utc_time = datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)
    
    subscription = create_mock_subscription(location=moscow_location)
    result = schedule_service.check_schedule(subscription, utc_time)
    
    # Check that local time is correct
    tz = pytz.timezone(moscow_location.timezone)
    expected_local = utc_time.astimezone(tz)
    assert result.current_time_local.hour == 15
    assert result.current_time_local.minute == 0


def test_utc_to_local_conversion_tokyo(schedule_service, tokyo_location):
    """Test UTC to Tokyo local time conversion."""
    # 2026-04-09 12:00:00 UTC = 2026-04-09 21:00:00 Tokyo (UTC+9)
    utc_time = datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)
    
    subscription = create_mock_subscription(location=tokyo_location)
    result = schedule_service.check_schedule(subscription, utc_time)
    
    assert result.current_time_local.hour == 21
    assert result.current_time_local.minute == 0


def test_utc_to_local_conversion_new_york(schedule_service, new_york_location):
    """Test UTC to New York local time conversion."""
    # 2026-04-09 12:00:00 UTC = 2026-04-09 08:00:00 New York (UTC-4 during DST)
    utc_time = datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)
    
    subscription = create_mock_subscription(location=new_york_location)
    result = schedule_service.check_schedule(subscription, utc_time)
    
    assert result.current_time_local.hour == 8
    assert result.current_time_local.minute == 0


# ============================================================================
# DELIVERY WINDOW TESTS - NORMAL OPERATION
# ============================================================================


def test_delivery_allowed_within_window(schedule_service, moscow_location):
    """Test delivery is allowed during active window."""
    # 12:00 UTC = 15:00 Moscow, which is within 08:00-20:00
    utc_time = datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)
    
    subscription = create_mock_subscription(
        active_from="08:00",
        active_to="20:00",
        location=moscow_location,
    )
    result = schedule_service.check_schedule(subscription, utc_time)
    
    assert result.is_allowed is True
    assert result.status == ScheduleStatus.ALLOWED
    assert result.next_allowed_time_utc is None


def test_delivery_blocked_before_window_opens(schedule_service, moscow_location):
    """Test delivery is blocked before window opens."""
    # 04:00 UTC = 07:00 Moscow, before 08:00 window
    utc_time = datetime(2026, 4, 9, 4, 0, 0, tzinfo=timezone.utc)
    
    subscription = create_mock_subscription(
        active_from="08:00",
        active_to="20:00",
        location=moscow_location,
    )
    result = schedule_service.check_schedule(subscription, utc_time)
    
    assert result.is_allowed is False
    assert result.status == ScheduleStatus.PENDING_WINDOW_CLOSED
    assert result.next_allowed_time_utc is not None
    
    # Next window opens at 08:00 Moscow = 05:00 UTC
    expected_open = datetime(2026, 4, 9, 5, 0, 0, tzinfo=timezone.utc)
    assert result.next_allowed_time_utc == expected_open


def test_delivery_blocked_after_window_closes(schedule_service, moscow_location):
    """Test delivery is blocked after window closes."""
    # 17:30 UTC = 20:30 Moscow, after 20:00 window
    utc_time = datetime(2026, 4, 9, 17, 30, 0, tzinfo=timezone.utc)
    
    subscription = create_mock_subscription(
        active_from="08:00",
        active_to="20:00",
        location=moscow_location,
    )
    result = schedule_service.check_schedule(subscription, utc_time)
    
    assert result.is_allowed is False
    assert result.status == ScheduleStatus.PENDING_WINDOW_CLOSED
    assert result.next_allowed_time_utc is not None
    
    # Next window opens tomorrow at 08:00 Moscow = 05:00 UTC
    # So it should be next day 05:00 UTC
    expected_open = datetime(2026, 4, 10, 5, 0, 0, tzinfo=timezone.utc)
    assert result.next_allowed_time_utc == expected_open


# ============================================================================
# BOUNDARY CONDITION TESTS
# ============================================================================


def test_boundary_exactly_at_window_start(schedule_service, moscow_location):
    """Test delivery is allowed exactly at window start time."""
    # Exactly 08:00 Moscow = 05:00 UTC
    utc_time = datetime(2026, 4, 9, 5, 0, 0, tzinfo=timezone.utc)
    
    subscription = create_mock_subscription(
        active_from="08:00",
        active_to="20:00",
        location=moscow_location,
    )
    result = schedule_service.check_schedule(subscription, utc_time)
    
    assert result.is_allowed is True
    assert result.status == ScheduleStatus.ALLOWED


def test_boundary_exactly_at_window_end(schedule_service, moscow_location):
    """Test delivery is blocked exactly at window end time (exclusive)."""
    # Exactly 20:00 Moscow = 17:00 UTC
    utc_time = datetime(2026, 4, 9, 17, 0, 0, tzinfo=timezone.utc)
    
    subscription = create_mock_subscription(
        active_from="08:00",
        active_to="20:00",
        location=moscow_location,
    )
    result = schedule_service.check_schedule(subscription, utc_time)
    
    # At 20:00, window is closed (exclusive end)
    assert result.is_allowed is False
    assert result.status == ScheduleStatus.PENDING_WINDOW_CLOSED


def test_boundary_one_second_before_window_start(schedule_service, moscow_location):
    """Test delivery is blocked one second before window start."""
    # 07:59:59 Moscow = 04:59:59 UTC
    utc_time = datetime(2026, 4, 9, 4, 59, 59, tzinfo=timezone.utc)
    
    subscription = create_mock_subscription(
        active_from="08:00",
        active_to="20:00",
        location=moscow_location,
    )
    result = schedule_service.check_schedule(subscription, utc_time)
    
    assert result.is_allowed is False


def test_boundary_one_minute_before_window_end(schedule_service, moscow_location):
    """Test delivery is allowed one minute before window end."""
    # 19:59 Moscow = 16:59 UTC
    utc_time = datetime(2026, 4, 9, 16, 59, 0, tzinfo=timezone.utc)
    
    subscription = create_mock_subscription(
        active_from="08:00",
        active_to="20:00",
        location=moscow_location,
    )
    result = schedule_service.check_schedule(subscription, utc_time)
    
    assert result.is_allowed is True


# ============================================================================
# NO-WINDOW (ALWAYS-ALLOWED) TESTS
# ============================================================================


def test_no_window_both_null(schedule_service, moscow_location):
    """Test delivery is allowed anytime when both window bounds are null."""
    utc_time = datetime(2026, 4, 9, 23, 59, 59, tzinfo=timezone.utc)
    
    subscription = create_mock_subscription(
        active_from=None,
        active_to=None,
        location=moscow_location,
    )
    result = schedule_service.check_schedule(subscription, utc_time)
    
    assert result.is_allowed is True
    assert result.status == ScheduleStatus.NO_WINDOW
    assert result.active_from_local is None
    assert result.active_to_local is None
    assert result.next_allowed_time_utc is None


def test_no_window_start_null(schedule_service, moscow_location):
    """Test delivery is allowed when window start is null."""
    utc_time = datetime(2026, 4, 9, 4, 0, 0, tzinfo=timezone.utc)
    
    subscription = create_mock_subscription(
        active_from=None,
        active_to="20:00",
        location=moscow_location,
    )
    result = schedule_service.check_schedule(subscription, utc_time)
    
    assert result.is_allowed is True
    assert result.status == ScheduleStatus.NO_WINDOW


def test_no_window_end_null(schedule_service, moscow_location):
    """Test delivery is allowed when window end is null."""
    utc_time = datetime(2026, 4, 9, 23, 0, 0, tzinfo=timezone.utc)
    
    subscription = create_mock_subscription(
        active_from="08:00",
        active_to=None,
        location=moscow_location,
    )
    result = schedule_service.check_schedule(subscription, utc_time)
    
    assert result.is_allowed is True
    assert result.status == ScheduleStatus.NO_WINDOW


# ============================================================================
# TIME PARSING TESTS
# ============================================================================


def test_parse_time_valid_format(schedule_service):
    """Test parsing valid HH:MM time format."""
    parsed = schedule_service._parse_time("14:30")
    assert parsed == time(14, 30)


def test_parse_time_midnight(schedule_service):
    """Test parsing midnight."""
    parsed = schedule_service._parse_time("00:00")
    assert parsed == time(0, 0)


def test_parse_time_end_of_day(schedule_service):
    """Test parsing 23:59."""
    parsed = schedule_service._parse_time("23:59")
    assert parsed == time(23, 59)


def test_parse_time_none(schedule_service):
    """Test parsing None."""
    parsed = schedule_service._parse_time(None)
    assert parsed is None


def test_parse_time_invalid_format_no_colon(schedule_service):
    """Test parsing invalid format without colon."""
    with pytest.raises(InvalidScheduleFormat):
        schedule_service._parse_time("1430")


def test_parse_time_invalid_format_too_many_parts(schedule_service):
    """Test parsing invalid format with too many parts."""
    with pytest.raises(InvalidScheduleFormat):
        schedule_service._parse_time("14:30:00")


def test_parse_time_invalid_hour(schedule_service):
    """Test parsing invalid hour > 23."""
    with pytest.raises(InvalidScheduleFormat):
        schedule_service._parse_time("24:00")


def test_parse_time_invalid_minute(schedule_service):
    """Test parsing invalid minute > 59."""
    with pytest.raises(InvalidScheduleFormat):
        schedule_service._parse_time("14:60")


def test_parse_time_invalid_type(schedule_service):
    """Test parsing invalid type (not string)."""
    with pytest.raises(InvalidScheduleFormat):
        schedule_service._parse_time(1430)


# ============================================================================
# VALIDATION TESTS
# ============================================================================


def test_invalid_window_start_equals_end(schedule_service):
    """Test that window with start == end raises error."""
    subscription = create_mock_subscription(
        active_from="12:00",
        active_to="12:00",
    )
    
    with pytest.raises(InvalidTimeWindow):
        schedule_service.check_schedule(
            subscription,
            datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
        )


def test_invalid_window_start_after_end(schedule_service):
    """Test that window with start > end raises error."""
    subscription = create_mock_subscription(
        active_from="20:00",
        active_to="08:00",
    )
    
    with pytest.raises(InvalidTimeWindow):
        schedule_service.check_schedule(
            subscription,
            datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
        )


def test_missing_timezone(schedule_service):
    """Test that missing timezone raises error."""
    location = MockLocation()
    location.timezone = None
    
    subscription = create_mock_subscription(location=location)
    
    with pytest.raises(MissingTimezone):
        schedule_service.check_schedule(
            subscription,
            datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
        )


def test_non_utc_timestamp_raises_error(schedule_service, moscow_location):
    """Test that non-UTC timestamp raises error."""
    subscription = create_mock_subscription(location=moscow_location)
    
    # Create Moscow local time without UTC marker
    tz = pytz.timezone(moscow_location.timezone)
    local_time = tz.localize(datetime(2026, 4, 9, 15, 0, 0))
    
    with pytest.raises(ValueError, match="must be in UTC"):
        schedule_service.check_schedule(subscription, local_time)


# ============================================================================
# NEXT DELIVERY WINDOW TESTS
# ============================================================================


def test_next_delivery_window_when_blocked(schedule_service, moscow_location):
    """Test getting next window when delivery is currently blocked."""
    # 04:00 UTC = 07:00 Moscow, which is before 08:00
    # Exact time: we'll use a known time to check the calculation
    utc_time = datetime(2026, 4, 9, 4, 0, 0, tzinfo=timezone.utc)
    
    subscription = create_mock_subscription(
        active_from="08:00",
        active_to="20:00",
        location=moscow_location,
    )
    
    result = schedule_service.get_next_delivery_window(subscription, utc_time)
    
    assert result is not None
    assert result.window_opens_at_utc == datetime(2026, 4, 9, 5, 0, 0, tzinfo=timezone.utc)
    assert result.window_closes_at_utc == datetime(2026, 4, 9, 17, 0, 0, tzinfo=timezone.utc)
    # in_minutes = (05:00 - 04:00) = 60 minutes
    assert result.in_minutes == 60


def test_next_delivery_window_when_allowed_returns_none(schedule_service, moscow_location):
    """Test that next window is None when delivery is currently allowed."""
    # 12:00 UTC = 15:00 Moscow, which is within 08:00-20:00
    utc_time = datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)
    
    subscription = create_mock_subscription(
        active_from="08:00",
        active_to="20:00",
        location=moscow_location,
    )
    
    result = schedule_service.get_next_delivery_window(subscription, utc_time)
    
    assert result is None  # No future window to schedule


def test_next_delivery_window_no_restrictions_returns_none(schedule_service, moscow_location):
    """Test that next window is None when there are no time restrictions."""
    utc_time = datetime(2026, 4, 9, 23, 59, 59, tzinfo=timezone.utc)
    
    subscription = create_mock_subscription(
        active_from=None,
        active_to=None,
        location=moscow_location,
    )
    
    result = schedule_service.get_next_delivery_window(subscription, utc_time)
    
    assert result is None  # No window to schedule


def test_next_delivery_window_after_hours(schedule_service, moscow_location):
    """Test next window calculation when it's after hours."""
    # 17:30 UTC = 20:30 Moscow, after 20:00 window
    utc_time = datetime(2026, 4, 9, 17, 30, 0, tzinfo=timezone.utc)
    
    subscription = create_mock_subscription(
        active_from="08:00",
        active_to="20:00",
        location=moscow_location,
    )
    
    result = schedule_service.get_next_delivery_window(subscription, utc_time)
    
    assert result is not None
    # Next window opens tomorrow at 08:00 Moscow = 05:00 UTC
    assert result.window_opens_at_utc == datetime(2026, 4, 10, 5, 0, 0, tzinfo=timezone.utc)
    # Window closes at 20:00 Moscow = 17:00 UTC
    assert result.window_closes_at_utc == datetime(2026, 4, 10, 17, 0, 0, tzinfo=timezone.utc)


# ============================================================================
# RESULT STRUCTURE TESTS
# ============================================================================


def test_schedule_check_result_all_fields_present(schedule_service, moscow_location):
    """Test that result contains all required fields."""
    utc_time = datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)
    
    subscription = create_mock_subscription(
        active_from="08:00",
        active_to="20:00",
        location=moscow_location,
    )
    result = schedule_service.check_schedule(subscription, utc_time)
    
    assert isinstance(result, ScheduleCheckResult)
    assert result.subscription_id == subscription.id
    assert isinstance(result.status, ScheduleStatus)
    assert isinstance(result.is_allowed, bool)
    assert result.current_time_local is not None
    assert result.active_from_local is not None or result.active_from_local is None
    assert result.reason is not None


def test_schedule_check_result_reason_descriptive(schedule_service, moscow_location):
    """Test that reason field is descriptive."""
    utc_time = datetime(2026, 4, 9, 4, 0, 0, tzinfo=timezone.utc)
    
    subscription = create_mock_subscription(
        active_from="08:00",
        active_to="20:00",
        location=moscow_location,
    )
    result = schedule_service.check_schedule(subscription, utc_time)
    
    assert "outside window" in result.reason.lower() or "pending" in result.reason.lower()
    assert result.reason is not None and len(result.reason) > 0
