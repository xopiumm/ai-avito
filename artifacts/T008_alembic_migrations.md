# T008: Alembic миграции для Weather Alerts

## Созданные файлы

1. **`migrations/env.py`** — Alembic конфигурация для работы с БД
2. **`migrations/versions/0001_initial_schema.py`** — первая миграция (создание таблиц)
3. **`migrations/__init__.py`** и **`migrations/versions/__init__.py`** — Python пакеты
4. **`alembic.ini`** — конфигурационный файл Alembic

## Структура миграций

```
migrations/
├── __init__.py
├── env.py                    # Alembic конфигурация
├── versions/
│   ├── __init__.py
│   └── 0001_initial_schema.py  # Первая миграция
```

## Таблицы, создаваемые миграцией

### locations (предусловие для subscriptions)

| Колонка | Тип | Назначение |
|---------|-----|-----------|
| id | Integer | PK |
| provider_location_key | String | Уникальный ключ от weather provider |
| display_name | String | Человеческое название |
| latitude | Float | Координата |
| longitude | Float | Координата |
| timezone | String | Timezone для расписания |
| created_at | DateTime | Timestamp создания |
| updated_at | DateTime | Timestamp обновления |

**Unique**: provider_location_key (по провайдеру)
**Индексы**: timezone

### subscriptions

| Колонка | Тип | Назначение |
|---------|-----|-----------|
| id | Integer | PK |
| user_id | String | Внешний ID пользователя |
| location_id | Integer | FK → locations |
| status | Enum | active/disabled/deleted |
| condition_mode | String | "ANY" по спецификации |
| schedule_timezone_source | String | "location" или "user" |
| active_from | String(HH:MM) | Начало окна доставки |
| active_to | String(HH:MM) | Конец окна доставки |
| created_at | DateTime | Timestamp создания |
| updated_at | DateTime | Timestamp обновления |
| deleted_at | DateTime | Мягкое удаление |

**Unique**: user_id, location_id, status (для активных)
**Индексы**: user_id, location_id, status
**FK Constraint**: location_id → locations.id

### subscription_conditions

| Колонка | Тип | Назначение |
|---------|-----|-----------|
| id | Integer | PK |
| subscription_id | Integer | FK → subscriptions (CASCADE) |
| type | Enum | temperature_below/above, rain_probability_above, wind_speed_above, severe_weather |
| threshold_value | Float | Числовое значение (-10, 70, etc) |
| threshold_unit | String | Единица (C, F, %, km/h) |
| severity_event_type | Enum | storm, hurricane, tornado, blizzard, extreme_heat, extreme_cold |
| created_at | DateTime | Timestamp создания |

**Check Constraints**:
- Для числовых типов (temp, rain, wind): threshold_value IS NOT NULL
- Для severe_weather: severity_event_type IS NOT NULL

**Индексы**: subscription_id, type
**FK Constraint**: subscription_id → subscriptions.id (CASCADE DELETE)

### delivery_channels

| Колонка | Тип | Назначение |
|---------|-----|-----------|
| id | Integer | PK |
| subscription_id | Integer | FK → subscriptions (CASCADE) |
| type | Enum | email, push, webhook |
| destination | String(500) | Email, token или URL |
| active | Boolean | Включен ли канал |
| failure_state | Enum | ok, failed, retrying |
| retry_count | Integer | Кол-во неудачных попыток подряд |
| last_failure_at | DateTime | Время последней ошибки |
| created_at | DateTime | Timestamp создания |
| updated_at | DateTime | Timestamp обновления |

**Индексы**: subscription_id, type, active, failure_state
**FK Constraint**: subscription_id → subscriptions.id (CASCADE DELETE)

## Использование Alembic

### Применить все миграции (upgrade)

```bash
# Применить все pending миграции
alembic upgrade head

# Применить только следующую миграцию
alembic upgrade +1

# Применить до конкретной миграции
alembic upgrade 0001
```

### Откатить миграции (downgrade)

```bash
# Откатить последнюю миграцию
alembic downgrade -1

# Откатить все миграции
alembic downgrade base

# Откатить до конкретной миграции
alembic downgrade 0001
```

### Сгенерировать миграцию (autogenerate)

```bash
# После изменения ORM моделей
alembic revision --autogenerate -m "Описание изменений"

# Это создаст новый файл в versions/
```

### Просмотреть текущее состояние

```bash
# Показать текущую версию в БД
alembic current

# Показать историю миграций
alembic history

# Показать SQL для следующей миграции
alembic upgrade head --sql
```

## Типы миграций

### Upgrade (0001_initial_schema.py)

Создает:
1. Таблицу locations
2. Таблицу subscriptions с FK на locations
3. Таблицу subscription_conditions с FK на subscriptions (CASCADE)
4. Таблицу delivery_channels с FK на subscriptions (CASCADE)
5. Все индексы и constraints

### Downgrade

Удаляет все таблицы в обратном порядке:
1. delivery_channels
2. subscription_conditions
3. subscriptions
4. locations
5. Все Enum типы (PostgreSQL)

## Первый запуск (пустая БД)

```bash
# 1. Убедиться, что БД запущена
docker-compose up -d

# 2. Создать БД (если используется другой пользователь)
createdb -U weather_user -E UTF8 weather_alerts

# 3. Применить миграции
alembic upgrade head

# 4. Проверить результат
psql -U weather_user -d weather_alerts -c "\\dt"
```

**Ожидаемый результат**:
```
                  List of relations
 Schema |          Name          | Type  | Owner
--------+------------------------+-------+-----------
 public | alembic_version        | table | weather_user
 public | delivery_channels      | table | weather_user
 public | locations              | table | weather_user
 public | subscription_conditions | table | weather_user
 public | subscriptions          | table | weather_user
```

## Интеграция с приложением

### ⚠️ ВАЖНО: Миграции должны запускаться отдельно

**Мигрирации НЕ должны запускаться автоматически при старте приложения!** Это может привести к race conditions в распределённых системах.

**Правильный подход:**
1. Запустить миграции `alembic upgrade head` как отдельный шаг деплоя/релиза
2. В приложении только использовать уже готовую схему БД

### Миграции как отдельный CLI шаг

```bash
# Перед деплоем: запустить миграции
alembic upgrade head

# Затем: запустить приложение
python -m uvicorn src.weather_alerts.main:app
```

### В app startup (main.py или lifespan)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
import logging

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Application starting. Ensure migrations are run: alembic upgrade head")
    yield
    # Shutdown
    logger.info("Application shutting down")

app = FastAPI(lifespan=lifespan)
```

### Альтернатива: CLI команда для миграций (если нужна автоматизация)

```python
import asyncio
from alembic.config import Config
from alembic import command

async def apply_migrations():
    """Apply pending migrations (call from CLI, not from app startup)."""
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")

# В CLI или скрипте деплоя:
# asyncio.run(apply_migrations())
```

## Env.py конфигурация

**Key features**:

1. **Auto imports**: Автоматически импортирует Base из config модуля
2. **Settings integration**: Использует DATABASE_URL из settings.db.url
3. **Online mode** (default): Выполняет миграции напрямую в БД
4. **Offline mode**: Генерирует SQL без применения (--sql флаг)
5. **Type comparison**: Сравнивает типы колонок при autogenerate
6. **Server defaults**: Сравнивает server defaults (func.now(), т.д.)

## Troubleshooting

### "Can't find target table"

Убедиться что:
- ORM模ели импортируются в env.py (через Base.metadata.reflect())
- Location модель существует (или создать ее)

### "Migration script failed"

```bash
# Проверить синтаксис миграции
alembic current

# Откатить и пересоздать
alembic downgrade -1
alembic upgrade +1
```

### PostgreSQL: "ALTER TABLE IF EXISTS"

Migration использует DROP IF EXISTS для совместимости с SQLite и PostgreSQL.

## Следующие шаги

После T008:
- **T009**: Pydantic schemas для API
- **T010**: SubscriptionService с CRUD
- **T011**: REST роуты для управления подписками
