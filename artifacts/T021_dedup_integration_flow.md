## T021 Integration Flow - Deduplication Gate

### Orchestration Flow with Dedup Check

```
orchestrate_notifications()  [ASYNC - NEW]
├─ Input: location_id, subscriptions[], forecast
├─ _filter_active_subscriptions()
│
└─ For each active subscription:
   │
   └─ _process_subscription()  [ASYNC - UPDATED]
      │
      ├─ Step 1: Evaluate conditions
      │  └─ condition_service.evaluate_subscription()
      │     Returns: ConditionEvaluationResult (matched, event_type)
      │
      ├─ Step 2: Check if conditions matched
      │  └─ If NOT matched → skip subscription
      │
      ├─ Step 3: Check delivery schedule
      │  └─ schedule_service.check_schedule()
      │     Returns: ScheduleCheckResult (is_allowed)
      │
      └─ Step 4: Route based on schedule
         │
         ├─ If schedule ALLOWED → _prepare_notifications_for_sending()  [ASYNC - NEW DEDUP]
         │  │
         │  ├─ Get active channels
         │  │
         │  └─ For each channel:
         │     │
         │     ├─ ┌─────────────────────────────────────────────────┐
         │     │  │  T021: DEDUP GATE (per-channel check)            │
         │     │  │                                                   │
         │     │  │  dedup_service.is_duplicate_and_mark(            │
         │     │  │    user_id,                                      │
         │     │  │    subscription_id,                              │
         │     │  │    channel.type,  ← KEY: per-channel!            │
         │     │  │    event_type                                    │
         │     │  │  )                                               │
         │     │  │                                                   │
         │     │  │  Redis operation (atomic):                       │
         │     │  │    SET dedup_key "1" EX=43200 NX=true            │
         │     │  │                                                   │
         │     │  │  Returns DuplicationStatus:                      │
         │     │  │  ├─ FIRST_OCCURRENCE (new mark set)              │
         │     │  │  ├─ DUPLICATE (found existing mark)              │
         │     │  │  └─ CHECK_FAILED (Redis error)                   │
         │     │  └─────────────────────────────────────────────────┘
         │     │
         │     ├─ If DUPLICATE → SKIP channel (no notification)
         │     ├─ If FIRST_OCCURRENCE → CREATE PreparedNotification
         │     └─ If CHECK_FAILED → CREATE anyway (conservative)
         │
         │  └─ Result: prepared_notifications[] (only non-duplicates)
         │
         └─ If schedule BLOCKED → _prepare_notifications_for_pending()
            (No dedup for pending - will check when window opens)
```

### Key Points of T021 Integration

1. **Location**: Dedup check is in `_prepare_notifications_for_sending()` just before creating notification

2. **Per-Channel Logic**: Each channel (email, push, webhook) checked independently
   - Different channels = different dedup keys
   - Notification can be sent to email but deduplicated for push

3. **Dedup Key Format**:
   ```
   dedup:{user_id}:{subscription_id}:{channel}:{event_type}
   ```

4. **Atomicity**: Redis SET with NX + EX (no race conditions)

5. **TTL Handling**: 12 hours automatic expiry (RedisTTL.DEDUP_WINDOW_SECONDS)

6. **Idempotency**: First call marks, subsequent calls find mark → same result

7. **Conservative on Errors**: GET_FAILED status still allows delivery (don't block on Redis)

### Changes Made (Minimal, Localized)

#### 1. Imports (4 lines added)
```python
from src.weather_alerts.services.deduplication_service import (
    DeduplicationService,
    DuplicationStatus,
)
```

#### 2. Docstring (5 lines added)
- Updated top-level docstring to mention T021 dedup integration
- Documented dedup window and per-channel logic

#### 3. __init__ (3 lines added)
```python
def __init__(
    ...
    deduplication_service: Optional[DeduplicationService] = None,  # NEW
):
    ...
    self.deduplication_service = deduplication_service or DeduplicationService()  # NEW
```

#### 4. Method Signatures (2 made async)
- `orchestrate_notifications()` → async (for _process_subscription to be async)
- `_process_subscription()` → async (for _prepare_notifications_for_sending to be async)
- `_prepare_notifications_for_sending()` → async (for dedup Redis calls)

#### 5. Core Integration (in _prepare_notifications_for_sending)

Before:
```python
for channel in active_channels:
    notification = PreparedNotification(...)
    result.prepared_notifications.append(notification)
```

After (with dedup gate):
```python
for channel in active_channels:
    # T021: DEDUP GATE - Check deduplication per channel
    dedup_result = await self.deduplication_service.is_duplicate_and_mark(
        user_id=subscription.user_id,
        subscription_id=subscription.id,
        channel=channel.type,  # ← per-channel!
        event_type=str(condition_result.event_type),
    )
    
    # Skip if duplicate
    if dedup_result and dedup_result.status == DuplicationStatus.DUPLICATE:
        continue
    
    # Create notification (only if first occurrence or error)
    notification = PreparedNotification(...)
    result.prepared_notifications.append(notification)
```

### Dedup Flow in Action

**Scenario 1: First notification**
```
Event: Temperature alert for User1, Subscription42
├─ Email channel
│  └─ Dedup check: FIRST_OCCURRENCE (mark set in Redis)
│     ✓ Email notification added to result
└─ Push channel
   └─ Dedup check: FIRST_OCCURRENCE (mark set in Redis)
      ✓ Push notification added to result

Result: 2 notifications prepared for sending
```

**Scenario 2: Same event 1 hour later (replay)**
```
Event: Same temperature alert replayed
├─ Email channel
│  └─ Dedup check: DUPLICATE (mark exists in Redis)
│     ✗ Email notification SKIPPED
└─ Push channel
   └─ Dedup check: DUPLICATE (mark exists in Redis)
      ✗ Push notification SKIPPED

Result: 0 notifications prepared (both deduplicated)
```

**Scenario 3: Different channel after 12 hours**
```
Event: Same temperature alert after 12h+ pass
├─ Email channel
│  └─ Dedup check: FIRST_OCCURRENCE (mark expired, new one set)
│     ✓ Email notification added to result
└─ Push channel (assumes different device)
   └─ Dedup check: FIRST_OCCURRENCE (mark expired, new one set)
      ✓ Push notification added to result

Result: 2 notifications prepared (dedup window expired)
```

### Spec Requirements Covered

✓ **Dedup gate before sending**: ✓ Gate is at start of _prepare_notifications_for_sending
✓ **Per-channel logic**: ✓ Each channel checked independently with channel.type in key
✓ **Prevent duplicate send**: ✓ DUPLICATE status skips notification creation
✓ **Atomicity**: ✓ Redis SET NX EX ensures atomic check-and-mark
✓ **Idempotency**: ✓ Repeated events return DUPLICATE on dedup try
✓ **12-hour window**: ✓ RedisTTL.DEDUP_WINDOW_SECONDS = 43200
✓ **After window expires**: ✓ Redis TTL automatically removes old marks

### Testing Points

1. **First occurrence**: Dedup returns FIRST_OCCURRENCE, notification created
2. **Duplicate within 12h**: Dedup returns DUPLICATE, notification skipped
3. **Different channel**: Same subscription, different channel = different key
4. **Redis error**: CHECK_FAILED still allows notification (conservative)
5. **After 12h**: New notification allowed (TTL expired)
