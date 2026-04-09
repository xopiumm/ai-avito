# T010: SubscriptionService для управления жизненным циклом подписок

**Date:** 2025-04-10  
**Task:** Implement SubscriptionService with business logic for subscription management  
**Status:** ✅ Complete

## Overview

Реализован сервисный слой для управления жизненным циклом подписок Weather Alerts с полной инкапсуляцией бизнес-логики, соблюдением инвариантов и правильной обработкой ошибок.

## Files Created

### 1. `src/weather_alerts/services/exceptions.py` (55 lines)

Доменные исключения (не HTTP!) для сервисного слоя:

```python
WeatherAlertsException          # Base exception

SubscriptionNotFound            # Подписка не найдена
SubscriptionAlreadyExists       # Активная подписка уже существует
SubscriptionAlreadyDeleted      # Подписка уже удалена
SubscriptionAlreadyDisabled     # Подписка уже отключена
SubscriptionAlreadyActive       # Подписка уже активна

LocationNotFound                # Локация не найдена
InvalidSubscriptionData         # Данные нарушают бизнес-правила
UnauthorizedSubscriptionAccess  # Пользователь не владеет подпиской
```

**Ключевой принцип:** Исключения отражают *бизнес-логику*, не HTTP статусы.
HTTP status mapping (400/401/404/409) — ответственность API слоя.

### 2. `src/weather_alerts/services/subscription_service.py` (520 lines)

Полный сервис с методами:

#### Методы управления

**`create(user_id, request) -> SubscriptionResponse`**
```python
# Бизнес-правила:
✅ Одна активная подписка на (user_id + location_id)
✅ Минимум 1 условие обязательно
✅ Минимум 1 канал доставки обязательно
✅ Новые подписки создаются с status=ACTIVE
✅ Автоматически создаёт связанные Condition и DeliveryChannel

# Пример:
request = CreateSubscriptionRequest(
    location=LocationSchema(id=123),
    conditions=[
        SubscriptionConditionCreateSchema(type="rain_probability_above", threshold_value=70),
    ],
    delivery_channels=[
        DeliveryChannelCreateSchema(type="email", destination="user@example.com"),
    ],
    schedule=ScheduleSchema(active_from="08:00", active_to="20:00")
)
subscription = await service.create("user_123", request)
# Возвращает: SubscriptionResponse с ID, conditions, channels
```

**`list(user_id) -> List[SubscriptionResponse]`**
```python
# Инвариант: Возвращает только status != DELETED (soft-delete фильтрация)
# Логика: Newest first (ORDER BY created_at DESC)
subscriptions = await service.list("user_123")
# Возвращает: [active, disabled] подписки, без deleted
```

**`get(user_id, subscription_id) -> SubscriptionResponse`**
```python
# Проверки:
✅ subscription существует
✅ user владеет subscription
# Возвращает: Полную подписку с условиями и каналами
subscription = await service.get("user_123", 1)
```

**`update(user_id, subscription_id, request) -> SubscriptionResponse`**
```python
# Семантика обновления:
✅ Все поля опциональны (partial update)
✅ Условия и каналы полностью заменяются (не merge)
✅ Нельзя обновлять deleted подписку
✅ Если поле не указано, сохраняется старое значение

# Пример - обновить только расписание:
update_req = UpdateSubscriptionRequest(
    schedule=ScheduleSchema(active_from="09:00", active_to="19:00")
)
# Условия и каналы не изменяются

# Пример - заменить все условия:
update_req = UpdateSubscriptionRequest(
    conditions=[
        SubscriptionConditionCreateSchema(type="temperature_below", threshold_value=-10),
    ]
)
# Старые условия удаляются, создаются новые
```

**`disable(user_id, subscription_id) -> SubscriptionResponse`**
```python
# Переход: ACTIVE -> DISABLED
# Эффект: Уведомления не отправляются, данные сохраняются
# Инвариант: status != ACTIVE raises SubscriptionAlreadyDisabled
subscription = await service.disable("user_123", 1)
```

**`enable(user_id, subscription_id) -> SubscriptionResponse`**
```python
# Переход: DISABLED -> ACTIVE
# Эффект: Возобновляет оценку условий и отправку уведомлений
# Инвариант: status != DISABLED raises SubscriptionAlreadyActive
subscription = await service.enable("user_123", 1)
```

**`delete(user_id, subscription_id) -> None`**
```python
# Soft-delete: status=DELETED + deleted_at=now()
# Инвариант: Двойное удаление raises SubscriptionAlreadyDeleted
# Инвариант: Удалённые подписки исключены из list()
# Бизнес-правило: Этот сервис НЕ отменяет pending/retry задачи
#                 (это ответственность очереди задач, если реализована)
await service.delete("user_123", 1)
```

#### Контроль доступа

```python
async def _authorize_user_subscription(user_id: str, subscription_id: int)
    # Проверяет:
    ✅ Подписка существует
    ✅ Пользователь владеет подпиской
    # Загружает отношения с selectinload для N+1 prevention
```

## Инварианты Системы (в коде задокументированы)

### 1. LIFECYCLE СТАТУСЫ
```
ACTIVE <--enable--> DISABLED
  |                    |
  +--delete--> DELETED
status != DELETED returned by list()
```

### 2. АВТОРИЗАЦИЯ
```
Каждая операция: проверка user_id владения
UnauthorizedSubscriptionAccess на нарушение
```

### 3. УНИКАЛЬНОСТЬ ЛОКАЦИИ
```
SELECT count(*) FROM subscriptions 
WHERE user_id = ? AND location_id = ? AND status = 'ACTIVE' 
должен быть <= 1 после create()
```

### 4. НЕПОЛНЫЕ ПОДПИСКИ
```
- Conditions: всегда >= 1 (не может быть пусто)
- Channels: всегда >= 1 (не может быть пусто)
Enforced at:
  1. API schema level (Pydantic min_items=1)
  2. Database level (NOT NULL foreign keys)
  3. Service validation
```

### 5. СЕМАНТИКА UPDATE
```
UpdateSubscriptionRequest(
    conditions=None,     # -> keep existing
    channels=None,       # -> keep existing
    schedule=None        # -> keep existing
)
UpdateSubscriptionRequest(
    conditions=[...],    # -> replace all conditions
    channels=[...],      # -> replace all channels
)
```

### 6. SOFT DELETE
```
deleted_at timestamp set только при status=DELETED
Data никогда не удаляется физически
list() фильтрует status != DELETED
```

### 7. ВРЕМЕННЫЕ МЕТКИ
```
created_at   -> установлена при создании, никогда не меняется
updated_at   -> установлена при создании, обновляется при любом изменении
deleted_at   -> установлена только при переходе status -> DELETED
```

### 8. БЕЗ HTTP ЛОГИКИ
```
Сервис НИКОГДА не возвращает HTTP статусы
Сервис НИКОГДА не использует FastAPI HTTPException
HTTP статус mapping -> ответственность API routes layer
Это позволяет переиспользовать сервис в других contexts (CLI, events, etc)
```

## Отношения с ORM Моделями

**Create cascading:**
```python
Subscription
  ├─ conditions: List[SubscriptionCondition]
  │   └─ FK subscription_id -> CASCADE DELETE
  └─ channels: List[DeliveryChannel]
      └─ FK subscription_id -> CASCADE DELETE
```

**Explicit relationship management:**
```python
# При create: явно добавляем в subscription.conditions и subscription.channels
# При update с новыми conditions:
1. DELETE FROM subscription_conditions WHERE subscription_id = ?
2. subscription.conditions.clear()
3. Добавляем новые объекты в subscription.conditions
4. flush() + refresh relationships

# Это более безопасно чем обновление на месте
```

## Интеграция с Pydantic Схемами

**Request -> Service -> ORM -> Response:**
```
CreateSubscriptionRequest (Pydantic)
    ↓ (со схемной валидацией)
SubscriptionService.create()
    ↓ (создаёт ORM модели)
SubscriptionModel + SubscriptionCondition + DeliveryChannel
    ↓ (flush + refresh)
SubscriptionResponse (Pydantic, via model_validate)
```

**Отношения типов:**
```python
# Enum alignment
API schema:       ConditionTypeEnum
Domain models:    ConditionType (ORM)
API response:     SubscriptionResponse (uses model_validate, ORM -> Pydantic)

# Same for DeliveryChannelType, SubscriptionStatus
```

## Контрольные Примеры

### Пример 1: Создание подписки
```python
from src.weather_alerts.services import SubscriptionService
from src.weather_alerts.api.schemas import CreateSubscriptionRequest

service = SubscriptionService(db_session)

request = CreateSubscriptionRequest(
    location=LocationSchema(id=1),
    conditions=[
        SubscriptionConditionCreateSchema(
            type=ConditionTypeEnum.RAIN_PROBABILITY_ABOVE,
            threshold_value=70
        )
    ],
    delivery_channels=[
        DeliveryChannelCreateSchema(
            type=DeliveryChannelTypeEnum.EMAIL,
            destination="user@example.com",
            active=True
        )
    ],
    schedule=ScheduleSchema(
        timezone_source="location",
        active_from="08:00",
        active_to="20:00"
    )
)

response = await service.create("user_123", request)
assert response.status == SubscriptionStatusEnum.ACTIVE
assert len(response.conditions) == 1
assert len(response.delivery_channels) == 1
```

### Пример 2: Ошибка авторизации
```python
# Пользователь user_456 пытается получить подписку user_123
try:
    await service.get("user_456", 1)
except UnauthorizedSubscriptionAccess as e:
    # Сервис выбрасывает доменное исключение
    # API layer преобразует в 403 Forbidden
    pass
```

### Пример 3: Обновление условий
```python
update_req = UpdateSubscriptionRequest(
    conditions=[
        SubscriptionConditionCreateSchema(
            type=ConditionTypeEnum.TEMPERATURE_BELOW,
            threshold_value=-15
        ),
        SubscriptionConditionCreateSchema(
            type=ConditionTypeEnum.SEVERE_WEATHER,
            severity_event_type=SeverityEventTypeEnum.HURRICANE
        )
    ]
)

response = await service.update("user_123", 1, update_req)
# Старые условия удалены, новые добавлены
assert len(response.conditions) == 2
```

### Пример 4: Мягкое удаление
```python
await service.delete("user_123", 1)

# Пытаемся получить
result = await service.list("user_123")
assert not any(sub.id == 1 for sub in result)  # 1 не в списке

# Попытка удалить еще раз -> ошибка
try:
    await service.delete("user_123", 1)
except SubscriptionAlreadyDeleted:
    pass
```

## Следующие Шаги

- **T011:** REST API routes в `src/weather_alerts/api/routes/subscriptions.py`
  - Использует `SubscriptionService` в route handlers
  - Отображает доменные исключения на HTTP статусы
  - Сервис НИКОГДА не знает о FastAPI/HTTP

- **T012:** FastAPI app в `src/weather_alerts/api/main.py`
  - Инициализирует routes, middleware, exception handlers

- **Phase 3+:** Weather evaluation, delivery channels, retry logic

## Dependencies

- **sqlalchemy** (2.0+): Async ORM with relationships
- **pydantic** (v2.5.0+): Request/response validation
- **python** (3.11+): Type hints, async/await

## Files Modified
- Created: `src/weather_alerts/services/subscription_service.py`
- Created: `src/weather_alerts/services/exceptions.py`
- Updated: `src/weather_alerts/services/__init__.py`

