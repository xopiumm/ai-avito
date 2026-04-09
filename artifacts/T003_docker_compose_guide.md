# T003: Docker Compose инфраструктура для Weather Alerts

## Созданный файл

**`docker-compose.yml`** — полная конфигурация для локального окружения

## Конфигурация

### PostgreSQL 16

| Параметр | Значение |
|----------|----------|
| **Image** | postgres:16-alpine |
| **Port** | 5432 |
| **User** | weather_user |
| **Password** | weather_pass |
| **Database** | weather_alerts |
| **Volume** | postgres_data (persisten) |
| **Healthcheck** | pg_isready каждые 5s |
| **Restart Policy** | unless-stopped |

### Redis 7

| Параметр | Значение |
|----------|----------|
| **Image** | redis:7-alpine |
| **Port** | 6379 |
| **Volume** | redis_data (persisten) |
| **Persistence** | AOF (appendonly) |
| **Max Memory** | 256mb с LRU eviction |
| **Healthcheck** | redis-cli ping каждые 5s |
| **Restart Policy** | unless-stopped |

**Примечание**: Redis использует один порт (6379). Разные DB индексы (0, 1, 2) используются в коде через REDIS_URL из .env.example:
- `redis://localhost:6379/0` — основное хранилище (дедупликация)
- `redis://localhost:6379/1` — Celery broker
- `redis://localhost:6379/2` — Celery result backend

## Соответствие .env.example

Все параметры docker-compose соответствуют дефолтным значениям в `.env.example`:

```env
# Database
DB_URL=postgresql+asyncpg://weather_user:weather_pass@localhost:5432/weather_alerts

# Redis
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
```

## Быстрый старт

### 1. Запустить контейнеры

```bash
docker-compose up -d
```

**Вывод:**
```
Creating weather_alerts_postgres ... done
Creating weather_alerts_redis   ... done
```

### 2. Проверить статус контейнеров

```bash
docker-compose ps
```

**Ожидаемый вывод:**
```
NAME                       COMMAND                  SERVICE    STATUS              PORTS
weather_alerts_postgres    "docker-entrypoint…"     postgres   Up (healthy)        0.0.0.0:5432->5432/tcp
weather_alerts_redis       "redis-server --ap…"     redis      Up (healthy)        0.0.0.0:6379->6379/tcp
```

**Примечание:** Статус `(healthy)` появляется через ~10-15 секунд после старта при успешном healthcheck.

## Проверка доступности

### PostgreSQL

**Через psql (если установлен):**
```bash
psql -h localhost -U weather_user -d weather_alerts -c "SELECT version();"
```

**Через Docker:**
```bash
docker-compose exec postgres psql -U weather_user -d weather_alerts -c "SELECT now();"
```

**Ожидаемый вывод:**
```
              now              
-------------------------------
 2026-04-09 12:34:56.123456+00
```

### Redis

**Через redis-cli:**
```bash
redis-cli -h localhost ping
```

**Ожидаемый вывод:**
```
PONG
```

**Через Docker:**
```bash
docker-compose exec redis redis-cli ping
```

**Проверить информацию:**
```bash
docker-compose exec redis redis-cli info server
```

## Проверка через Python

```python
import psycopg2
import redis

# PostgreSQL
try:
    conn = psycopg2.connect(
        host="localhost",
        user="weather_user",
        password="weather_pass",
        database="weather_alerts"
    )
    print("✅ PostgreSQL OK")
    conn.close()
except Exception as e:
    print(f"❌ PostgreSQL ERROR: {e}")

# Redis
try:
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    result = r.ping()
    print(f"✅ Redis OK: {result}")
except Exception as e:
    print(f"❌ Redis ERROR: {e}")
```

## Остановка контейнеров

### Остановить, но сохранить данные

```bash
docker-compose stop
```

### Перезапустить контейнеры

```bash
docker-compose start
```

### Остановить и удалить контейнеры (но сохранить volumes)

```bash
docker-compose down
```

### Удалить все (контейнеры, сеть и volumes)

```bash
docker-compose down -v
```

⚠️ **Внимание:** `down -v` удалит все данные в БД и Redis!

## Логирование

### Просмотреть логи PostgreSQL

```bash
docker-compose logs postgres
```

### Просмотреть логи Redis

```bash
docker-compose logs redis
```

### Следить за логами в реальном времени

```bash
docker-compose logs -f
```

## Синтеграция с приложением

### 1. Убедиться, что .env установлен корректно

```bash
cp .env.example .env
```

### 2. Запустить миграции БД (когда будут готовы)

```bash
# После создания Alembic миграций
alembic upgrade head
```

### 3. Запустить API сервис

```bash
python -m uvicorn src.weather_alerts.api.main:app --reload
```

### 4. Запустить Celery воркеры

```bash
celery -A src.weather_alerts.workers.celery_app worker --loglevel=info
```

## Типичные проблемы

### Порт уже занят

```bash
# Найти процесс, занимающий порт 5432
lsof -i :5432

# Найти процесс, занимающий порт 6379
lsof -i :6379

# Убить процесс
kill -9 <PID>
```

### Контейнер не запускается

```bash
# Проверить логи
docker-compose logs postgres
docker-compose logs redis

# Перестроить образы
docker-compose down
docker-compose up -d --build
```

### Данные не сохраняются после перезагрузки

**Проверить volumes:**
```bash
docker volume ls | grep weather_alerts

# Должны быть:
# weather_alerts_postgres_data
# weather_alerts_redis_data
```

### Connection refused при подключении из Python

1. Убедиться, что контейнеры запущены: `docker-compose ps`
2. Убедиться, что healthcheck прошел: статус должен быть `Up (healthy)` или `Up`
3. Проверить, не заблокирован ли firewall портам 5432 и 6379
4. Убедиться что используются правильные хосты в подключении (localhost, не 127.0.0.1)

## Roadmap

После T003:
- T004: Добавить зависимости в requirements.txt (psycopg2, asyncpg, redis, celery)
- T005-T006: Реализовать подключение к БД и Redis в коде
- T007-T008: ORM модели и миграции Alembic
