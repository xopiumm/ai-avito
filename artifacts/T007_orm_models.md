# T007: ORM модели Weather Alerts

## Созданные файлы

1. **`src/weather_alerts/domain/models/subscription.py`** (350+ строк)
   - Три основные ORM модели
   - Енумы для типов

2. **`src/weather_alerts/domain/models/__init__.py`** — экспорт моделей

3. **Обновлено `domain/__init__.py`** — экспорт моделей на уровне пакета

## ORM Модели

### 1. Subscription

**Таблица**: `subscriptions`

**Назначение**: Пользовательская конфигурация уведомлений для одной локации.

**Ключевые поля**:

| Поле | Тип | Назначение |
|------|-----|-----------|
| `id` | Integer | Primary key |
| `user_id` | String(255) | Внешний ID пользователя (управляется в другой системе) |
| `location_id` | FK → locations | Локация для мониторинга |
| `status` | Enum | Состояние (active, disabled, deleted) |
| `condition_mode` | String | "ANY" — любое условие вызывает оповещение |
| `schedule_timezone_source` | String | Источник timezone ("location" или "user") |
| `active_from` | String(HH:MM) | Начало окна доставки в локальном времени |
| `active_to` | String(HH:MM) | Конец окна доставки в локальном времени |
| `created_at` | DateTime | Время создания |
| `updated_at` | DateTime | Время последнего изменения |
| `deleted_at` | DateTime | Время удаления (soft delete) |

**Связи**:
- `conditions` → List[SubscriptionCondition] — условия, вызывающие оповещения
- `channels` → List[DeliveryChannel] — каналы доставки

**Валидация**:
- Уникальность: user_id + location_id + status (для активных подписок)
- Мягкое удаление: status='deleted' с timestamp в deleted_at

**Примеры**:
```python
# Создать подписку
subscription = Subscription(
    user_id="usr_123",
    location_id=45,
    status=SubscriptionStatus.ACTIVE,
    active_from="08:00",
    active_to="20:00",
)

# Добавить условия (ANY логика)
condition1 = SubscriptionCondition(
    subscription_id=subscription.id,
    type=ConditionType.TEMPERATURE_BELOW,
    threshold_value=-10,
    threshold_unit="C",
)
subscription.conditions.append(condition1)

# Добавить канал доставки
channel = DeliveryChannel(
    subscription_id=subscription.id,
    type=DeliveryChannelType.EMAIL,
    destination="user@example.com",
    active=True,
)
subscription.channels.append(channel)
```

### 2. SubscriptionCondition

**Таблица**: `subscription_conditions`

**Назначение**: Одно погодное условие в подписке (temperature_below, rain_probability, etc).

**Ключевые поля**:

| Поле | Тип | Назначение |
|------|-----|-----------|
| `id` | Integer | Primary key |
| `subscription_id` | FK → subscriptions | Родительская подписка |
| `type` | Enum | Тип условия (temperature_below, temperature_above, rain_probability_above, wind_speed_above, severe_weather) |
| `threshold_value` | Float | Числовое значение для сравнения (e.g., -10 для температуры, 70 для % дождя) |
| `threshold_unit` | String(20) | Единица измерения (C, F, %, km/h) |
| `severity_event_type` | Enum | Для severe_weather: какой вид (storm, hurricane, tornado, blizzard, extreme_heat, extreme_cold) |
| `created_at` | DateTime | Время создания (immutable) |

**Валидация**:
- Для числовых условий (temperature, rain, wind) — обязателен threshold_value
- Для severe_weather — обязателен severity_event_type

**Примеры**:
```python
# Условие: температура ниже -10°C
cond1 = SubscriptionCondition(
    subscription_id=1,
    type=ConditionType.TEMPERATURE_BELOW,
    threshold_value=-10,
    threshold_unit="C",
)

# Условие: вероятность дождя > 70%
cond2 = SubscriptionCondition(
    subscription_id=1,
    type=ConditionType.RAIN_PROBABILITY_ABOVE,
    threshold_value=70,
    threshold_unit="%",
)

# Условие: суровая погода (hurricane)
cond3 = SubscriptionCondition(
    subscription_id=1,
    type=ConditionType.SEVERE_WEATHER,
    threshold_value=None,  # Не применяется для severe_weather
    severity_event_type=SeverityEventType.HURRICANE,
)
```

### 3. DeliveryChannel

**Таблица**: `delivery_channels`

**Назначение**: Канал доставки оповещений (email, push, webhook).

**Ключевые поля**:

| Поле | Тип | Назначение |
|------|-----|-----------|
| `id` | Integer | Primary key |
| `subscription_id` | FK → subscriptions | Родительская подписка |
| `type` | Enum | Тип канала (email, push, webhook) |
| `destination` | String(500) | Адрес: email, токен устройства или URL webhook |
| `active` | Boolean | Включен ли канал для отправки |
| `failure_state` | Enum | Статус: ok, failed, retrying |
| `retry_count` | Integer | Кол-во неудачных попыток подряд |
| `last_failure_at` | DateTime | Время последней ошибки |
| `created_at` | DateTime | Время создания |
| `updated_at` | DateTime | Время последнего изменения |

**Примеры**:
```python
# Email канал
email_channel = DeliveryChannel(
    subscription_id=1,
    type=DeliveryChannelType.EMAIL,
    destination="user@example.com",
    active=True,
)

# Push канал
push_channel = DeliveryChannel(
    subscription_id=1,
    type=DeliveryChannelType.PUSH,
    destination="fcm_device_token_xyz",
    active=True,
)

# Webhook канал
webhook_channel = DeliveryChannel(
    subscription_id=1,
    type=DeliveryChannelType.WEBHOOK,
    destination="https://user-app.example.com/weather-alerts",
    active=True,
)
```

## Enum типы

| Enum | Значения |
|------|----------|
| **SubscriptionStatus** | active, disabled, deleted |
| **ConditionType** | temperature_below, temperature_above, rain_probability_above, wind_speed_above, severe_weather |
| **SeverityEventType** | storm, hurricane, tornado, blizzard, extreme_heat, extreme_cold |
| **DeliveryChannelType** | email, push, webhook |
| **FailureState** | ok, failed, retrying |

## Соответствие спецификации

✅ **Все поля из data-model.md** — в моделях  
✅ **Relationship благоустроили** — с cascade delete-orphan для условий/каналов  
✅ **Валидация в БД** — CheckConstraints для правил  
✅ **Soft delete для Subscription** — status + deleted_at  
✅ **Timezone для расписания** — active_from/active_to в локальном времени  
✅ **Failure tracking** — failure_state, retry_count, last_failure_at в DeliveryChannel  
✅ **ANY логика для условий** — условия хранятся как список (любое вызывает оповещение)  

## Использование в коде

### В FastAPI маршрутах

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.weather_alerts.domain.models import Subscription, SubscriptionCondition, DeliveryChannel

@app.get("/subscriptions/{subscription_id}")
async def get_subscription(subscription_id: int, session: AsyncSession = Depends(get_db_session)):
    result = await session.execute(
        select(Subscription).where(Subscription.id == subscription_id)
    )
    subscription = result.scalar_one_or_none()
    
    # Relationships уже загружены (lazy="selectin")
    for condition in subscription.conditions:
        print(f"Condition: {condition.type} = {condition.threshold_value}")
    
    for channel in subscription.channels:
        print(f"Channel: {channel.type} -> {channel.destination}")
    
    return subscription
```

### Создание подписки с условиями

```python
async def create_subscription_with_conditions(
    user_id: str,
    location_id: int,
    session: AsyncSession,
):
    sub = Subscription(
        user_id=user_id,
        location_id=location_id,
        status=SubscriptionStatus.ACTIVE,
        active_from="08:00",
        active_to="20:00",
    )
    
    # Условия (ANY логика)
    sub.conditions.append(SubscriptionCondition(
        type=ConditionType.TEMPERATURE_BELOW,
        threshold_value=-10,
        threshold_unit="C",
    ))
    
    # Каналы доставки
    sub.channels.append(DeliveryChannel(
        type=DeliveryChannelType.EMAIL,
        destination=user_email,
        active=True,
    ))
    
    session.add(sub)
    await session.commit()
    return sub
```

## Следующие шаги

- **T008**: Alembic миграции для создания таблиц
- **T009**: Pydantic schemas для API (create/update/response)
- **T010**: SubscriptionService с CRUD операциями
