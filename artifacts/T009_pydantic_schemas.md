# T009: Pydantic Schemas for Subscription API

**Date:** 2025-04-10  
**Task:** Add Pydantic v2 schemas for subscription API endpoints  
**Status:** ✅ Complete

## Overview

Created comprehensive Pydantic v2 request/response schemas for the Weather Alerts Subscription API with full validation and type hints. Schemas align with ORM models and API contract specifications.

## Files Created

### 1. `src/weather_alerts/api/schemas/subscription.py` (485 lines)

Complete schema implementation with:

#### Enum Classes (for validation)
- **ConditionTypeEnum**: `temperature_below`, `temperature_above`, `rain_probability_above`, `wind_speed_above`, `severe_weather`
- **SeverityEventTypeEnum**: `storm`, `hurricane`, `tornado`, `blizzard`, `extreme_heat`, `extreme_cold`
- **DeliveryChannelTypeEnum**: `email`, `push`, `webhook`
- **SubscriptionStatusEnum**: `active`, `disabled`, `deleted`

#### Nested Schemas

##### LocationSchema
```python
- id: int (location database ID)
- display_name: Optional[str]
```

##### SubscriptionConditionCreateSchema
```python
- type: ConditionTypeEnum (required)
- threshold_value: Optional[float] (required for numeric types)
- threshold_unit: Optional[str] (C, F, %, km/h)
- severity_event_type: Optional[SeverityEventTypeEnum]

Validation:
✅ condition type is supported
✅ threshold_value required for numeric types
✅ severity_event_type required for severe_weather type
✅ mutual exclusivity: numeric types vs severe_weather
```

##### SubscriptionConditionResponseSchema
- Extends ConditionCreate with: `id`, `created_at`

##### DeliveryChannelCreateSchema
```python
- type: DeliveryChannelTypeEnum (required)
- destination: str (email, token, or webhook URL)
- active: bool (default True)

Validation:
✅ channel type is supported
✅ destination is non-empty, <= 500 chars
✅ email validation: contains @ and .
✅ webhook validation: starts with http:// or https://, >= 10 chars
```

##### DeliveryChannelResponseSchema
- Extends ChannelCreate with: `id`, `failure_state`, `retry_count`, `last_failure_at`, `created_at`, `updated_at`

##### ScheduleSchema
```python
- timezone_source: Literal["location", "user"] (default "location")
- active_from: Optional[str] (HH:MM format, None = no restriction)
- active_to: Optional[str] (HH:MM format)

Validation:
✅ HH:MM format (00-23 hours, 00-59 minutes)
✅ active_from < active_to (cross-midnight not supported)
```

#### Request Schemas

##### CreateSubscriptionRequest
```python
- location: LocationSchema (required)
- conditions: List[SubscriptionConditionCreateSchema] (min_items=1, required)
- schedule: ScheduleSchema (default empty schedule)
- delivery_channels: List[DeliveryChannelCreateSchema] (min_items=1, required)

Validation:
✅ At least one condition
✅ At least one delivery channel
```

##### UpdateSubscriptionRequest
```python
- schedule: Optional[ScheduleSchema]
- conditions: Optional[List[SubscriptionConditionCreateSchema]] (min_items=1 if provided)
- delivery_channels: Optional[List[DeliveryChannelCreateSchema]] (min_items=1 if provided)

Validation:
✅ All fields optional (partial update)
✅ If provided, lists must not be empty
```

#### Response Schemas

##### SubscriptionResponse (complete)
```python
- id: int
- user_id: str
- location: LocationSchema
- status: SubscriptionStatusEnum
- condition_mode: Literal["ANY"]
- schedule: ScheduleSchema
- conditions: List[SubscriptionConditionResponseSchema]
- delivery_channels: List[DeliveryChannelResponseSchema]
- created_at: datetime
- updated_at: datetime
- deleted_at: Optional[datetime]
```

##### SubscriptionListItem (summary)
```python
- id: int
- user_id: str
- location: LocationSchema
- status: SubscriptionStatusEnum
- conditions_count: int
- channels_count: int
- created_at: datetime
- updated_at: datetime
```

#### Error Response Schemas

- **ErrorDetail**: `field` (optional), `message`
- **ErrorResponse**: `status_code`, `message`, `details` (optional list)

### 2. `src/weather_alerts/api/schemas/__init__.py` (50 lines)

Public API exports all schema classes for clean imports:
```python
from .subscription import (
    ConditionTypeEnum,
    CreateSubscriptionRequest,
    DeliveryChannelResponseSchema,
    SubscriptionResponse,
    ...
)
```

## Key Design Decisions

### 1. Validation Strategy
- **Field validators** for individual field validation (enum support, format checks)
- **Model validators** for cross-field validation (condition requirements, schedule window)
- **No business logic** in schemas (only data validation per requirements)

### 2. Type Safety
- All Pydantic models use `from_attributes=True` for ORM compatibility
- Clear `Optional` types for nullable fields
- Literal types for single-value enums (`timezone_source`)

### 3. Request/Response Separation
- Create schemas: minimal fields required for submission
- Response schemas: include all fields + timestamps + IDs
- Update schemas: all fields optional for partial updates

### 4. Nested Validation
- Conditions require type-specific validation (numeric vs severe weather)
- Channels validate destination format based on type
- Schedule validates time window logic

### 5. API Contract Alignment
Schemas mirror structure from `api-contract.md`:
```json
POST /api/v1/subscriptions {
  "location": { "id": "..." },
  "conditions": [{ "type": "...", "threshold": 70 }],
  "schedule": { "timezone": "location", "activeFrom": "08:00" },
  "deliveryChannels": [{ "type": "email", "address": "..." }]
}
```

## Validation Examples

### Valid Condition Create
```python
SubscriptionConditionCreateSchema(
    type="temperature_below",
    threshold_value=-10,
    threshold_unit="C"
)
```

### Invalid - Missing Threshold
```python
# Raises: "threshold_value is required for type=temperature_below"
SubscriptionConditionCreateSchema(
    type="temperature_below"
)
```

### Valid Severe Weather
```python
SubscriptionConditionCreateSchema(
    type="severe_weather",
    severity_event_type="hurricane"
)
```

### Invalid - Mixed Requirement
```python
# Raises: "threshold_value should not be set for type=severe_weather"
SubscriptionConditionCreateSchema(
    type="severe_weather",
    threshold_value=70,
    severity_event_type="hurricane"
)
```

### Valid Email Channel
```python
DeliveryChannelCreateSchema(
    type="email",
    destination="user@example.com",
    active=True
)
```

### Invalid Email
```python
# Raises: "Invalid email address: invalid"
DeliveryChannelCreateSchema(
    type="email",
    destination="invalid"
)
```

### Invalid Webhook URL
```python
# Raises: "Webhook URL must start with http:// or https://"
DeliveryChannelCreateSchema(
    type="webhook",
    destination="example.com/webhook"
)
```

## Dependencies

- **pydantic** (v2.5.0+): Core schema validation
- **python** (3.11+): Dataclass-like syntax, type hints

## Integration Points

### Used By
- T010: SubscriptionService will use schemas for CRUD operations
- T011: API routes will use schemas for request/response serialization
- T012: FastAPI app will use schemas in dependency injection

### Uses
- ORM models: Field types and names aligned with Subscription/SubscriptionCondition/DeliveryChannel
- Enums: ConditionType, DeliveryChannelType, etc. from domain models

## Next Steps

- **T010**: Implement SubscriptionService with CRUD methods
- **T011**: Create REST routes in `src/weather_alerts/api/routes/subscriptions.py`
- **T012**: Set up FastAPI app in `src/weather_alerts/api/main.py`

## Files Modified
- Created: `src/weather_alerts/api/schemas/subscription.py`
- Updated: `src/weather_alerts/api/schemas/__init__.py`

