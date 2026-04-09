## T022 - Pending Notification Service Integration

### Pending Notification Model

```python
PendingNotificationState {
    pending_id: str                               # Unique ID: user_sub_event_timestamp
    user_id: str                                  # User who owns subscription
    subscription_id: int                          # Which subscription
    location_id: int                              # Which location
    event_type: EventType                         # temperature_alert, rain_alert, etc.
    matched_conditions_count: int                 # 1+ conditions matched
    window_opens_at_utc: datetime                 # When to release for delivery
    window_closes_at_utc: datetime                # When window closes
    source_forecast_timestamp: datetime           # Forecast timestamp
    created_at_utc: datetime                      # When pending was created
    expires_at_utc: datetime                      # When pending auto-expires (7 days)
    channels: List[{id, type, destination}]      # Email, push, webhook destinations
}
```

### Storage

**Location**: Redis (no DB persistence)
**Key Format**: `pending:{user_id}:{subscription_id}:{pending_id}`
**Value**: JSON-serialized PendingNotificationState
**TTL**: 7 days (604800 seconds)

Example:
```
Key:   pending:user_123:42:user_123_42_temperature_alert_1712693400000
Value: {
         "pending_id": "user_123_42_temperature_alert_1712693400000",
         "user_id": "user_123",
         "subscription_id": 42,
         "location_id": 1,
         "event_type": "temperature_alert",
         "matched_conditions_count": 1,
         "window_opens_at_utc": "2026-04-10T08:00:00+00:00",
         "window_closes_at_utc": "2026-04-10T20:00:00+00:00",
         "source_forecast_timestamp": "2026-04-09T21:30:00+00:00",
         "created_at_utc": "2026-04-09T21:35:00+00:00",
         "expires_at_utc": "2026-04-16T21:35:00+00:00",
         "channels": [
           {"id": 1, "type": "email", "destination": "user@example.com"},
           {"id": 2, "type": "push", "destination": "device_token_xyz"}
         ]
       }
TTL: 604800 (expires 2026-04-16 21:35:00 UTC)
```

### State Transitions

```
                         ┌─────────────────┐
                         │   Event occurs  │
                         │ (conditions met)│
                         └────────┬────────┘
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │ Check delivery schedule │
                    └────────┬────────────────┘
                             │
                ─────────────┼─────────────
                │                         │
                ▼                         ▼
          WINDOW OPEN              WINDOW CLOSED
                │                         │
                │                         ▼
           (T021)               ┌──────────────────┐
            SEND                │ create_pending() │
         ready-to-send          └────────┬─────────┘
                                        │
                                        ▼
                              ┌──────────────────┐
                              │   STORED in      │
                              │   Redis (7 days) │──────┐
                              └────────┬─────────┘      │
                                       │               │
          ┌────────────────────────────┼────────────────┘
          │        (scheduler wakes)   │
          │   Window opens (next day)  │
          ▼                            ▼
┌─────────────────────┐    ┌──────────────────┐
│ release_pending()   │    │   TTL expires    │
└────────┬────────────┘    │  (7 days pass)   │
         │                 └──────────────────┘
         ▼                          │
    ┌─────────────┐               │
    │  RELEASED   │               ▼
    │  for        │          Auto-deleted
    │  delivery   │
    └─────────────┘

Alternative: Subscription deleted/disabled
         │
         ▼
┌──────────────────────────┐
│cancel_pending_for_       │
│subscription()            │
└────────┬─────────────────┘
         │
         ▼
    Pending deleted
```

### Service Methods

#### 1. create_pending()

**When**: Orchestrator detects conditions match but schedule window is CLOSED

**Called from**: `notification_orchestrator._prepare_notifications_for_pending()`

**Parameters**:
```python
await pending_service.create_pending(
    user_id="user_123",
    subscription_id=42,
    location_id=1,
    event_type=EventType.TEMPERATURE_ALERT,
    matched_conditions_count=1,
    window_opens_at_utc=datetime(..., 2026-04-10 08:00),
    window_closes_at_utc=datetime(..., 2026-04-10 20:00),
    source_forecast_timestamp=datetime(..., 2026-04-09 21:30),
    channels=[
        {"id": 1, "type": "email", "destination": "user@example.com"},
        {"id": 2, "type": "push", "destination": "device_token"}
    ]
)
```

**Returns**: `PendingOperationResult` with:
- `status=PendingStatus.STORED` (success)
- `pending_state` with all details
- `reason` explaining when it will release

**Redis Operation**:
```
SET pending:user_123:42:user_123_42_temperature_alert_1712693400000 
    <JSON> 
    EX 604800
```

#### 2. release_pending()

**When**: Scheduler wakes up at window.opens_at_utc

**Called from**: Pending scheduler worker (future T023)

**Parameters**:
```python
results = await pending_service.release_pending(
    user_id="user_123",
    subscription_id=42,
)
```

**Returns**: List of `PendingOperationResult` with:
- `status=PendingStatus.RELEASED` for each pending found
- `pending_state` with all details ready for delivery
- Each pending deleted from Redis after retrieval

**Workflow**:
1. SCAN Redis for all keys matching `pending:user_123:42:*`
2. GET each key, deserialize JSON
3. Return PendingNotificationState
4. DELETE the key from Redis

#### 3. cancel_pending_for_subscription()

**When**: Subscription is DELETED or DISABLED

**Called from**: `subscription_service.delete_subscription()` or `disable_subscription()`

**Parameters**:
```python
count = await pending_service.cancel_pending_for_subscription(subscription_id=42)
```

**Returns**: int - number of pending notifications cancelled

**Workflow**:
1. Build pattern `pending:*:42:*` (all pending for subscription 42)
2. SCAN all matching keys
3. DELETE all found keys
4. Return count

**Redis Operations**:
```
SCAN cursor MATCH pending:*:42:* COUNT 100
DELETE key1 key2 key3 ...
```

### Supporting Methods

#### get_pending()
Retrieve a single pending notification by ID (for auditing/debugging)

#### list_pending_for_subscription()
List all pending for a subscription (admin/debugging)

#### cancel_pending()
Cancel a single pending by ID (targeted cancellation)

### Integration Points

#### 1. Orchestrator Integration (T021)

**In**: `notification_orchestrator._prepare_notifications_for_pending()`

**Current code**:
```python
def _prepare_notifications_for_pending(self, subscription, condition_result, ...):
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
```

**Integration point** (future T023):
```python
# After orchestrator runs, call pending service:
for pending_request in orchestration_result.pending_requests:
    # Get active channels
    channels = [
        {"id": ch.id, "type": ch.type, "destination": ch.destination}
        for ch in subscription.channels if ch.active
    ]
    
    # Create pending
    await pending_service.create_pending(
        user_id=subscription.user_id,
        subscription_id=pending_request.subscription_id,
        location_id=pending_request.location_id,
        event_type=pending_request.event_type,
        matched_conditions_count=pending_request.matched_conditions_count,
        window_opens_at_utc=pending_request.window_opens_at_utc,
        window_closes_at_utc=pending_request.window_closes_at_utc,
        source_forecast_timestamp=pending_request.source_forecast_timestamp,
        channels=channels,
    )
```

#### 2. Subscription Service Integration

**In**: `subscription_service.delete_subscription()`

```python
async def delete_subscription(self, user_id, subscription_id):
    # ... delete subscription from DB
    
    # T022: Cancel pending notifications
    await pending_service.cancel_pending_for_subscription(subscription_id)
    
    # Also clean up dedup marks (T020)
    await dedup_service.clear_subscription_dedup(subscription_id)
```

**In**: `subscription_service.disable_subscription()`

```python
async def disable_subscription(self, user_id, subscription_id):
    # ... update subscription status to DISABLED
    
    # T022: Cancel pending notifications (spec requirement)
    await pending_service.cancel_pending_for_subscription(subscription_id)
```

#### 3. Scheduler Integration (future T023)

**New worker**: `scheduled_pending_notification_worker.py`

```python
async def process_pending_notifications():
    # Get all subscriptions with pending notifications
    # For each subscription
    pending_results = await pending_service.release_pending(user_id, subscription_id)
    
    for result in pending_results:
        if result.status == PendingStatus.RELEASED:
            pending = result.pending_state
            
            # Check if subscription still exists and is active
            subscription = await subscription_service.get(pending.subscription_id)
            if not subscription or subscription.status != ACTIVE:
                # Subscription deleted/disabled, skip
                continue
            
            # Get current forecast (may have changed)
            forecast = await weather_provider.get_forecast(pending.location_id)
            
            # Re-evaluate conditions (is alert still valid?)
            condition_result = condition_service.evaluate_subscription(...)
            if not condition_result.matched:
                # Condition no longer met, discard pending
                continue
            
            # Prepare notifications for sending (bypass schedule check, already open)
            for channel in pending.channels:
                notification = PreparedNotification(...)
                await delivery_service.send(notification)
```

### Data Flow Diagram

```
┌──────────────────┐
│ Weather Event    │
│ detected         │
└────────┬─────────┘
         │
         ▼
┌─────────────────────────────┐
│ NotificationOrchestrator    │
│ orchestrate_notifications() │
└────────┬────────────────────┘
         │
    ┌────┴─────┬──────────┐
    │           │          │
    ▼           ▼          ▼
READY_TO_SEND   PENDING    SKIPPED
    │           │
    │           └────────┬──────────────┐
    │                    ▼              ▼
    │          PendingNotificationRequest
    │                    │
    │                    ├─ user_id
    │                    ├─ subscription_id
    │                    ├─ event_type
    │                    ├─ window_opens_at_utc
    │                    └─ channels
    │                    │
    │                    ▼
    │        ┌───────────────────────┐
    │        │ PendingNotification   │
    │        │ Service.create_       │
    │        │ pending()             │
    │        └───────┬───────────────┘
    │                │
    │        ┌───────▼──────────┐
    │        │ Redis STORED     │
    │        │ TTL: 7 days      │
    │        └───────┬──────────┘
    │                │
    └────────┬───────┴──────────────│
             │                      │
             ▼                      ▼
    DeliveryService           Scheduler
    send_prepared()           (next day)
                              │
                              ▼
                    ┌─────────────────┐
                    │ PendingService  │
                    │ .release_       │
                    │ pending()       │
                    └────────┬────────┘
                             │
                    ┌────────▼───────┐
                    │ Re-evaluate    │
                    │ (if changed)   │
                    └────────┬───────┘
                             │
                    ┌────────▼──────────┐
                    │ DeliveryService   │
                    │ send()            │
                    └───────────────────┘
```

### Spec Requirements Met

✓ **FR-008**: Translate notifications to pending if window is closed
✓ **FR-008**: Send in next window if event still valid
✓ **Pending cancellation**: cancel_pending_for_subscription() on delete/disable
✓ **Subscription deletion during pending**: All pending cancelled immediately
✓ **Spec requirement**: "Удаление подписки во время pending отменяет дальнейшие попытки"

### Error Handling

1. **Redis unavailable**: Operations return OPERATION_FAILED status, don't crash
2. **JSON serialization error**: Individual pending skipped, continue with others
3. **Subscription already deleted**: Ignored gracefully (SCAN finds nothing)
4. **Partial failures**: Some pending released successfully, others fail individually

### Future Enhancements (Not in T022)

- **T023**: Pending notification scheduler worker
- **T024**: Delivery retry logic (exponential backoff)
- **T025**: Pending notification storage in DB (if audit required)
- **Events**: Subscribe to pending release events for async processing
