# Быстрый старт: Weather Alerts API

Полнофункциональный сервис подписок на погодные уведомления. Управляет подписками, расписаниями доставки, переиспользованием уведомлений и доставкой многоканальных уведомлений.

## 📋 Предварительные требования

- **Python:** 3.13+ (протестировано на 3.13.7)
- **Docker & Docker Compose:** для PostgreSQL и Redis (рекомендуется) или локальная установка:
  - PostgreSQL 14+
  - Redis 7+
- **Точка входа URL weather provider:** для реальных данных (опционально для разработки)

## 🚀 Процедура запуска

### 1️⃣ Клонирование и подготовка окружения

```bash
# Клонируйте репозиторий
git clone https://github.com/ai-course-avito/itmo-practice-xopiumm.git
cd itmo-practice-xopiumm

# Создайте виртуальное окружение
python3 -m venv .venv
source .venv/bin/activate  # На Windows: .venv\Scripts\activate
```

### 2️⃣ Установка зависимостей

```bash
# Установите Python dependencies
pip install -r requirements.txt

# Проверьте установку (должна пройти вывод версий)
python -c "import fastapi; import sqlalchemy; import celery; print('✓ All dependencies installed')"
```

### 3️⃣ Подъём инфраструктуры (PostgreSQL + Redis)

#### Вариант A: Docker Compose (рекомендуется)

```bash
# Убедитесь, что Docker запущен
docker --version
docker-compose --version

# Поднимите контейнеры (PostgreSQL на :5432, Redis на :6379)
docker-compose up -d

# Проверьте, что сервисы готовы
docker-compose ps  # Должны быть UP оба контейнера
sleep 3  # Дайте БД время для инициализации
```

#### Вариант B: Локальная установка PostgreSQL + Redis

```bash
# macOS (Homebrew)
brew install postgresql redis
brew services start postgresql
brew services start redis

# Linux (Ubuntu/Debian)
sudo apt-get install postgresql postgresql-contrib redis-server
sudo service postgresql start
sudo service redis-server start

# Создайте БД вручную (если нужно):
# createdb -U postgres weather_alerts
```

### 4️⃣ Применение miграций БД

```bash
# Убедитесь, что используется правильный путь
export DB_URL="postgresql+asyncpg://weather_user:weather_pass@localhost:5432/weather_alerts"
# ИЛИ на Windows:
# set DB_URL=postgresql+asyncpg://weather_user:weather_pass@localhost:5432/weather_alerts

# Примените миграции Alembic
alembic upgrade head

# Проверьте результат (должны быть созданы все таблицы):
PGPASSWORD=weather_pass psql -U weather_user -d weather_alerts -h localhost -c "\dt"
```

### 5️⃣ Запуск API сервера

В отдельном терминале:

```bash
# Активируйте виртуальное окружение (если ещё не активировано)
source .venv/bin/activate

# Вариант А: Через скрипт (автоматический setup)
bash scripts/run_dev.sh

# Вариант Б: Напрямую Uvicorn (если скрипт не работает)
uvicorn src.weather_alerts.api.main:app --reload --host 0.0.0.0 --port 8000
```

**Ожидаемый результат:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

**Откройте в браузере:**
- Swagger UI документация: http://localhost:8000/docs
- ReDoc документация: http://localhost:8000/redoc
- Health check: http://localhost:8000/health

### 6️⃣ Запуск Celery Worker (для фоновых задач доставки)

В **третьем** отдельном терминале:

```bash
# Активируйте виртуальное окружение
source .venv/bin/activate

# Запустите worker (процесс будет работать постоянно)
celery -A src.weather_alerts.workers.celery_app worker \
  --loglevel=info \
  --queues=delivery,default \
  --concurrency=4

# Expected output:
# -------------- celery@<hostname> v5.3.x ------
# --- ***** -----
# -- celery @ 0.0.0 (reply_time: 0.0ms)
# - ... [Tasks] ...
# - ... [Worker Online] ...
```

⚠️ **Важно:** Worker должен быть запущен постоянно для доставки уведомлений. Если worker не запущен, уведомления будут накапливаться в очереди.

### 7️⃣ Запуск тестов

```bash
# Активируйте виртуальное окружение
source .venv/bin/activate

# Запустите все тесты (unit + integration)
pytest tests/ -v

# Запустите только unit тесты
pytest tests/test_*.py -v

# Запустите только integration тесты
pytest tests/integration/ -v

# Запустите с покрытием (coverage report)
pytest tests/ --cov=src/weather_alerts --cov-report=html

# Откройте отчет: open htmlcov/index.html
```

**Ожидаемый результат:**
```
====== test session starts ======
collected 268 tests
tests/test_condition_evaluation_service.py::... PASSED [1%]
...
====== 268 passed in 12.34s ======
```

## 🔄 Smoke-тест (проверка работоспособности)

Полный цикл проверки системы:

### Сценарий 1: Создание подписки и проверка доставки

```bash
# 1. Создайте подписку через API
curl -X POST http://localhost:8000/alerts/subscriptions \
  -H "User-ID: test_user_1" \
  -H "Content-Type: application/json" \
  -d '{
    "location": {"id": 1},
    "conditions": [{"type": "temperature_below", "threshold_value": -10}],
    "delivery_channels": [
      {"type": "email", "destination": "user@example.com", "active": true}
    ],
    "schedule": {
      "active_from": "00:00",
      "active_to": "23:59",
      "timezone_source": "location"
    }
  }'

# 2. Получите ID подписки из ответа (например, 123)

# 3. Список ваших подписок
curl -X GET http://localhost:8000/alerts/subscriptions \
  -H "User-ID: test_user_1"

# 4. Ожидайте получить:
# - ID подписки
# - Статус: "active"
# - Все каналы доставки в списке
```

### Сценарий 2: Проверка расписания (Schedule Window)

```bash
# 1. Создайте новую подписку с узким расписанием (14:00-16:00 UTC)
curl -X POST http://localhost:8000/alerts/subscriptions \
  -H "User-ID: test_user_2" \
  -H "Content-Type: application/json" \
  -d '{
    "location": {"id": 2},
    "conditions": [{"type": "rain_probability_above", "threshold_value": 70}],
    "delivery_channels": [
      {"type": "push", "destination": "device_token_123", "active": true}
    ],
    "schedule": {
      "active_from": "14:00",
      "active_to": "16:00",
      "timezone_source": "location"
    }
  }'

# 2. Если вы создаёте подписку вне этого окна (например, в 22:00):
# - Уведомление должно быть создано как PENDING (не отправлено сразу)
# - При открытии окна (в 14:00 завтра) уведомление будет отправлено

# 3. Если вы создаёте подписку внутри окна:
# - Уведомление отправляется немедленно
```

### Сценарий 3: Проверка многоканальной доставки

```bash
# 1. Создайте подписку с тремя каналами
curl -X POST http://localhost:8000/alerts/subscriptions \
  -H "User-ID: test_user_3" \
  -H "Content-Type: application/json" \
  -d '{
    "location": {"id": 3},
    "conditions": [{"type": "wind_speed_above", "threshold_value": 20}],
    "delivery_channels": [
      {"type": "email", "destination": "user@example.com", "active": true},
      {"type": "push", "destination": "device_token_456", "active": true},
      {"type": "webhook", "destination": "https://example.com/alert", "active": true}
    ],
    "schedule": {
      "active_from": "06:00",
      "active_to": "22:00",
      "timezone_source": "location"
    }
  }'

# 2. Проверьте логи Celery worker
# - Должны быть три независимых delivery задачи
# - Если одна канал не удасться, остальные всё равно будут попытаны

# 3. Если один канал недоступен (например, вебхук вернёт 500):
# - Этот канал попытается переотправить (retry с exponential backoff)
# - Email и push отправятся нормально
```

### Сценарий 4: Проверка дедупликации

```bash
# 1. Отправьте два одинаковых уведомления в пределах 12 часов
# 2. Первое должно быть доставлено
# 3. Второе должно быть ПРОПУЩЕНО (deduplicated)

# Проверка в логах:
# - First: "Delivered" ✓
# - Second: "Skipped (duplicate within 12h)" ✓
```

### Сценарий 5: Отключение и удаление подписки

```bash
# 1. Отключите подписку (pause)
curl -X POST http://localhost:8000/alerts/subscriptions/{subscription_id}/pause \
  -H "User-ID: test_user_1"

# 2. Проверьте, что новые уведомления не отправляются
# 3. Возобновите подписку (resume)
curl -X POST http://localhost:8000/alerts/subscriptions/{subscription_id}/resume \
  -H "User-ID: test_user_1"

# 4. Удалите подписку (soft delete)
curl -X DELETE http://localhost:8000/alerts/subscriptions/{subscription_id} \
  -H "User-ID: test_user_1"

# 5. Проверьте, что она не появляется в списке
```

## 📊 Проверочный список перед merge

- [ ] Все 3 типа каналов (email, push, webhook) работают независимо
- [ ] Расписание (schedule) соблюдается (раннее уведомление → pending, вовремя → sent)
- [ ] Дедупликация работает (повторное событие в 12ч → skipped)
- [ ] Логи содержат correlation_id всех операций
- [ ] Unit тесты (tests/test_*.py): все passed ✓
- [ ] Integration тесты (tests/integration/): все passed ✓
- [ ] Smoke тесты выше: все сценарии работают ✓

## 🐛 Отладка и общие проблемы

### Проблема: "Connection refused" к PostgreSQL

```bash
# Проверьте, что контейнер запущен
docker-compose ps

# Если не запущен:
docker-compose up -d

# Если уже был запущен, перезагрузите:
docker-compose restart postgres
```

### Проблема: "Connection refused" к Redis

```bash
# Проверьте Redis
docker-compose ps

# Перезагрузите Redis:
docker-compose restart redis
```

### Проблема: Миграции не применяются

```bash
# Проверьте версию Alembic migration
alembic current

# Откатитесь к базе и примените заново:
alembic downgrade base
alembic upgrade head
```

### Проблема: Worker не запускается

```bash
# Проверьте, что Redis запущен
redis-cli ping  # Должен вернуть PONG

# Проверьте, что Celery может выполнять задачи
celery -A src.weather_alerts.workers.celery_app inspect active
```

### Проблема: Тесты падают

```bash
# Убедитесь, что PostgreSQL имеет правильное расширение UUID
psql -U weather_user -d weather_alerts -c "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";"

# Очистите БД тестирования и переу састе:
pytest tests/ --tb=short -v
```

## 📚 Дополнительные ресурсы

- **API Documentation:** http://localhost:8000/docs (Swagger UI)
- **Spec документация:** specs/001-weather-alerts/
- **Code documentation:** Каждый файл содержит docstrings
- **Logs:** Check stdout/stderr вашего worker и API процессов

## 🎯 Следующие шаги

1. Измените `WEATHER_PROVIDER_API_KEY` на реальный ключ API
2. Настройте email/push/webhook endpoints на ваши сервисы
3. Проверьте логирование и добавьте monitoring
4. Готовьтесь к production deployment (используйте Alembic вместо init_db)