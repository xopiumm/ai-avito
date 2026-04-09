# T004: Зависимости для Weather Alerts

## Обновлено: requirements.txt

Расструктурирован файл с четким разделением runtime и dev/test зависимостей, специфичных для Weather Alerts.

## Runtime Dependencies

### Web Framework

| Пакет | Версия | Назначение |
|-------|--------|-----------|
| **fastapi** | 0.104.1 | REST API framework с async поддержкой |
| **uvicorn** | 0.24.0 | ASGI server для запуска FastAPI |
| **python-multipart** | 0.0.6 | Парсинг multipart/form-data |

### Configuration & Validation

| Пакет | Версия | Назначение |
|-------|--------|-----------|
| **pydantic** | 2.5.0 | Валидация данных и type hints |
| **pydantic-settings** | 2.1.0 | Загрузка конфигурации из окружения |
| **python-dotenv** | 1.0.0 | Загрузка переменных из .env файла |

### Database & ORM

| Пакет | Версия | Назначение |
|-------|--------|-----------|
| **sqlalchemy** | ≥2.0.0 | SQL toolkit с async support |
| **asyncpg** | ≥0.29.0 | **Async** PostgreSQL driver (рекомендуется SQLAlchemy) |
| **psycopg2-binary** | ≥2.9.0 | PostgreSQL adapter для синхронных операций и миграций |
| **alembic** | ≥1.13.0 | Управление SQL миграциями БД |

### Cache & Task Queue

| Пакет | Версия | Назначение |
|-------|--------|-----------|
| **redis** | ≥5.0.0 | Redis клиент для deduplication и кеширования |
| **celery** | ≥5.3.0 | Distributed task queue для фоновых доставок |

### HTTP & Integrations

| Пакет | Версия | Назначение |
|-------|--------|-----------|
| **httpx** | ≥0.25.2 | Async HTTP клиент для external API (weather, email, push, webhook) |

### CLI

| Пакет | Версия | Назначение |
|-------|--------|-----------|
| **click** | ≥8.1.0 | Фреймворк для CLI утилит (testing, manual operations) |

## Dev & Test Dependencies

### Testing

| Пакет | Версия | Назначение |
|-------|--------|-----------|
| **pytest** | ≥7.0.0 | Test runner для unit и integration тестов |
| **pytest-asyncio** | ≥0.21.1 | Поддержка async тестов в pytest |
| **pytest-cov** | ≥4.0.0 | Reporting code coverage |

### Code Quality

| Пакет | Версия | Назначение |
|-------|--------|-----------|
| **flake8** | ≥6.0.0 | Linter для проверки стиля и ошибок |
| **black** | ≥23.0.0 | Автоматический formatter кода |
| **isort** | ≥5.12.0 | Сортировщик import statements |

## Optional (для других практик, не требуется для Weather Alerts)

- **sqlmodel**: ORM комбинирующийся Pydantic + SQLAlchemy
- **websockets**: WebSocket поддержка для real-time уведомлений (будущее расширение)
- **numpy, pandas, matplotlib**: Data science tools
- **jupyter, ipykernel**: Интерактивные ноутбуки
- **flask**: Альтернативный веб-фреймворк

## Обоснование выборов

### Почему asyncpg вместо psycopg2?

- **asyncpg** — асинхронный драйвер, рекомендуется SQLAlchemy для async applications
- Лучше latency и throughput для конкурентных операций
- **psycopg2-binary** оставлена для синхронных операций в миграциях и CLI

### Почему Celery для фоновых задач?

- Стандарт в Python экосистеме для distributed task queues
- Гибкие retry policies с exponential backoff
- Изоляция каналов доставки (каждый канал — отдельная task)
- Интеграция с Redis как broker

### Почему Redis?

- Нативный TTL для deduplication (12 часов)
- Быстрые атомарные операции для горячего пути dedup-проверок
- Broker и result backend для Celery

### Почему не включены?

- **ORM миграции**: используется Alembic как стандарт
- **Message queue альтернативы**: Celery + Redis достаточно для текущего объема
- **Tracer/observability**: будут добавлены в Phase 8 (структурированное логирование)
- **Database connection pooling**: встроено в SQLAlchemy

## Установка

### Только runtime зависимости:

```bash
pip install fastapi uvicorn pydantic pydantic-settings sqlalchemy asyncpg psycopg2-binary alembic redis celery httpx python-dotenv click
```

### С dev/test зависимостями:

```bash
pip install -r requirements.txt
```

## Проверка установки

```python
# В Python shell
import fastapi
import pydantic
import sqlalchemy
import asyncpg
import redis
import celery
import httpx

print("✅ Все зависимости установлены!")
```

## Следующие шаги (Phases 2-3)

- T005: Реализовать Database connection в `src/weather_alerts/config/database.py`
- T006: Redis client и utilities в `src/weather_alerts/config/redis.py`
- T007: ORM модели в `src/weather_alerts/domain/models/subscription.py`
- T008: Alembic миграции
