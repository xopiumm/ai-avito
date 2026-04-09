# T006: Redis клиент и утилиты ключей

## Созданный файл

**`src/weather_alerts/config/redis.py`** (240+ строк) — Redis async клиент и централизованный builder ключей

## Ключевые компоненты

### 1. Redis Client Factory

```python
from src.weather_alerts.config import get_redis_client

redis = get_redis_client()
await redis.set("key", "value", ex=3600)
```

**Особенности**:
- Ленивая инициализация (создается при первом обращении)
- `decode_responses=True` — возвращает строки вместо bytes
- `health_check_interval=30` — проверка соединения каждые 30 секунд
- Подключение по REDIS_URL из settings

### 2. RedisKeyBuilder — Централизованный builder ключей

Все ключи следуют формату: `{namespace}:{category}:{identifiers}`

#### Dedup ключи

```python
key = RedisKeyBuilder.dedup_key(
    user_id="user123",
    subscription_id=42,
    channel="email",
    event_type="temperature_below"
)
# Returns: "dedup:user123:42:email:temperature_below"
```

**Назначение**: 
- Предотвращение отправки дубликатов одного уведомления
- Проверяется перед каждой попыткой доставки
- TTL: 12 часов (по спецификации)
- Если уведомление отправлено, ключ сохраняется в Redis с TTL
- После срока можно отправить снова при повторном выполнении условия

#### Pending notification ключи

```python
key = RedisKeyBuilder.pending_notification_key(
    user_id="user123",
    subscription_id=42,
    event_id="event_20260409_001"
)
# Returns: "pending:user123:42:event_20260409_001"
```

**Назначение**:
- Хранение уведомлений, ожидающих доставки
- Используется когда:
  - Окно расписания закрыто (например, доставка с 08:00-20:00, событие произошло в 21:00)
  -需要ручной retry после сбоя
- TTL: 7 дней (достаточно для retry)
- Значение: serialized JSON с данными события

#### Pending по подписке (для удаления)

```python
pattern = RedisKeyBuilder.pending_by_subscription_key(subscription_id=42)
# Returns: "pending:*:42:*"

# Использование для очистки при удалении подписки:
async for key in redis.scan_iter(match=pattern):
    await redis.delete(key)
```

#### Retry metadata ключи

```python
key = RedisKeyBuilder.retry_metadata_key(task_id="task_abc123")
# Returns: "retry:task_abc123"
```

**Назначение**:
- Хранение метаданных о retry попытках
- Что хранится:
  - Количество попыток
  - Последняя ошибка
  - Время следующего retry
  - Состояние exponential backoff
- TTL: 24 часа

### 3. RedisTTL — предопределенные TTL значения

| Константа | Значение | Назначение |
|-----------|----------|-----------|
| **DEDUP_WINDOW_SECONDS** | 43200 (12ч) | Окно дедупликации по спеку |
| **PENDING_NOTIFICATION_SECONDS** | 604800 (7 дней) | Хранение pending уведомлений |
| **RETRY_METADATA_SECONDS** | 86400 (24ч) | Метаданные retry попыток |
| **TEMPORARY_SECONDS** | 300 (5 мин) | Временные координационные ключи |

### 4. Утилиты

```python
from src.weather_alerts.config import ping_redis, close_redis

# Проверить доступность Redis
is_healthy = await ping_redis()

# Закрыть соединение (при shutdown)
await close_redis()
```

## Использование в коде

### В Deduplication Service

```python
from src.weather_alerts.config import get_redis_client, RedisKeyBuilder, RedisTTL

async def check_and_mark_duplicate(
    user_id: str,
    subscription_id: int,
    channel: str,
    event_type: str,
) -> bool:
    redis = get_redis_client()
    key = RedisKeyBuilder.dedup_key(user_id, subscription_id, channel, event_type)
    
    # Check if notification already sent
    exists = await redis.exists(key)
    
    if not exists:
        # Mark as sent with 12-hour TTL
        await redis.setex(key, RedisTTL.DEDUP_WINDOW_SECONDS, "1")
        return False  # Not a duplicate, proceed
    
    return True  # Duplicate, skip delivery
```

### В Pending Notification Service

```python
import json
from src.weather_alerts.config import get_redis_client, RedisKeyBuilder, RedisTTL

async def store_pending_notification(
    user_id: str,
    subscription_id: int,
    event_id: str,
    notification_data: dict,
) -> None:
    redis = get_redis_client()
    key = RedisKeyBuilder.pending_notification_key(user_id, subscription_id, event_id)
    
    await redis.setex(
        key,
        RedisTTL.PENDING_NOTIFICATION_SECONDS,
        json.dumps(notification_data),
    )


async def get_pending_for_subscription(subscription_id: int) -> list[dict]:
    redis = get_redis_client()
    pattern = RedisKeyBuilder.pending_by_subscription_key(subscription_id)
    
    pending = []
    async for key in redis.scan_iter(match=pattern):
        data = await redis.get(key)
        if data:
            pending.append(json.loads(data))
    
    return pending


async def cleanup_pending_on_subscription_delete(subscription_id: int) -> int:
    """Remove all pending for deleted subscription."""
    redis = get_redis_client()
    pattern = RedisKeyBuilder.pending_by_subscription_key(subscription_id)
    
    keys = []
    async for key in redis.scan_iter(match=pattern):
        keys.append(key)
    
    if keys:
        return await redis.delete(*keys)
    return 0
```

### В FastAPI Startup

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.weather_alerts.config import ping_redis, close_redis

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if not await ping_redis():
        raise RuntimeError("Redis is not accessible")
    yield
    # Shutdown
    await close_redis()

app = FastAPI(lifespan=lifespan)
```

## Формат ключей

| Ключ | Формат | Пример | TTL | Значение |
|-----|--------|--------|-----|----------|
| **Dedup** | `dedup:{user_id}:{sub_id}:{channel}:{event_type}` | `dedup:user123:42:email:temperature_below` | 12h | `"1"` или флаг |
| **Pending** | `pending:{user_id}:{sub_id}:{event_id}` | `pending:user123:42:evt_001` | 7d | JSON (event data) |
| **Pending pattern** | `pending:*:{sub_id}:*` | `pending:*:42:*` | - | (scan pattern) |
| **Retry meta** | `retry:{task_id}` | `retry:task_abc123` | 24h | JSON (retry state) |

## Конфигурация из settings

- **REDIS_URL**: `redis://localhost:6379/0` (дефолт)
- **REDIS_DEDUP_TTL_SECONDS**: 43200 (12 часов)
- **REDIS_SOCKET_TIMEOUT**: 5 секунд

## Особенности

✅ **Async Redis client** — redis.asyncio для non-blocking операций  
✅ **Ленивая инициализация** — клиент создается при первом обращении  
✅ **Decode responses** — возвращает строки, а не bytes  
✅ **Health check** — автоматическая проверка соединения каждые 30s  
✅ **Централизованные ключи** — единое место для управления форматом  
✅ **TTL константы** — переиспользуемые значения для всех операций  
✅ **Pattern support** — поддержка scan_iter для удаления по уникальным запросам  

## Следующие шаги

- **T007**: Создать ORM модели (Subscription, SubscriptionCondition, DeliveryChannel)
- **T008**: Alembic миграции
- **T020 (Phase 6)**: Реализовать DeduplicationService с использованием этих утилит
- **T022 (Phase 6)**: Реализовать PendingNotificationService
