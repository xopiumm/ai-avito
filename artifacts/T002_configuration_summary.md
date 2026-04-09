# T002: Конфигурация Weather Alerts

## Создано

### 1. `src/weather_alerts/config/settings.py`
Конфигурационный модуль на основе Pydantic v2 Settings с поддержкой окружения, БД, Redis, провайдеров доставки и Celery.

**Структура сеттингов:**
- `DatabaseSettings` — PostgreSQL с asyncpg
- `RedisSettings` — Redis для дедупликации (TTL 12 часов)
- `WeatherProviderSettings` — Интеграция с weather API (OpenWeatherMap)
- `EmailSettings` — Email доставка
- `PushSettings` — Push-уведомления
- `WebhookSettings` — Webhook доставка с retry
- `CelerySettings` — Celery task queue (broker и result backend на Redis)
- `APISettings` — FastAPI server параметры
- `Settings` — корневой класс, объединяющий все секции

**Функции:**
- `get_settings()` — ленивая загрузка глобального экземпляра
- `reload_settings()` — для тестирования

### 2. `src/weather_alerts/config/__init__.py`
Экспортирует основные классы и функции.

### 3. `.env.example`
Пример файла конфигурации для локальной разработки.

## Итоговые переменные окружения

### ENVIRONMENT
- **ENVIRONMENT** — Окружение (development, staging, production)

### API Configuration
| Переменная | Значение по умолчанию | Назначение |
|------------|----------------------|-----------|
| API_HOST | 0.0.0.0 | Адрес привязки сервера |
| API_PORT | 8000 | Порт API |
| API_TITLE | Weather Alerts API | Название API |
| API_VERSION | 1.0.0 | Версия API |
| API_DEBUG | false | Режим отладки |
| API_LOG_LEVEL | INFO | Уровень логирования (DEBUG/INFO/WARNING/ERROR/CRITICAL) |
| API_REQUEST_TIMEOUT_SECONDS | 30 | Таймаут запросов в секундах |

### Database (PostgreSQL)
| Переменная | Значение по умолчанию | Назначение |
|------------|----------------------|-----------|
| DB_URL | postgresql+asyncpg://weather_user:weather_pass@localhost:5432/weather_alerts | Строка подключения |
| DB_ECHO | false | Логирование SQL запросов |
| DB_POOL_SIZE | 20 | Размер пула соединений |
| DB_MAX_OVERFLOW | 10 | Макс. дополнительных соединений |

### Redis
| Переменная | Значение по умолчанию | Назначение |
|------------|----------------------|-----------|
| REDIS_URL | redis://localhost:6379/0 | Строка подключения |
| REDIS_DEDUP_TTL_SECONDS | 43200 | TTL для ключей дедупликации (12 часов) |
| REDIS_SOCKET_TIMEOUT | 5 | Таймаут сокета в секундах |

### Weather Provider (OpenWeatherMap)
| Переменная | Значение по умолчанию | Назначение |
|------------|----------------------|-----------|
| WEATHER_PROVIDER_BASE_URL | https://api.openweathermap.org/data/2.5 | Base URL провайдера |
| WEATHER_PROVIDER_API_KEY | your-actual-api-key-here | API ключ (необходимо заполнить) |
| WEATHER_PROVIDER_TIMEOUT_SECONDS | 10 | Таймаут запросов |
| WEATHER_PROVIDER_RETRY_ATTEMPTS | 3 | Количество повторов |

### Email Delivery
| Переменная | Значение по умолчанию | Назначение |
|------------|----------------------|-----------|
| EMAIL_PROVIDER_URL | https://api.mailgun.net | URL email-провайдера (Mailgun, SendGrid и т.д.) |
| EMAIL_API_KEY | your-email-provider-api-key | API ключ (необходимо заполнить) |
| EMAIL_FROM_ADDRESS | alerts@weather-service.local | Адрес отправителя |
| EMAIL_TIMEOUT_SECONDS | 10 | Таймаут запросов |

### Push Notification Delivery
| Переменная | Значение по умолчанию | Назначение |
|------------|----------------------|-----------|
| PUSH_PROVIDER_URL | https://api.pushservice.local | URL push-провайдера (Firebase, OneSignal и т.д.) |
| PUSH_API_KEY | your-push-provider-api-key | API ключ (необходимо заполнить) |
| PUSH_TIMEOUT_SECONDS | 10 | Таймаут запросов |

### Webhook Delivery
| Переменная | Значение по умолчанию | Назначение |
|------------|----------------------|-----------|
| WEBHOOK_DELIVERY_TIMEOUT_SECONDS | 30 | Таймаут webhook HTTP запросов |
| WEBHOOK_MAX_RETRIES | 5 | Макс. количество повторов |
| WEBHOOK_RETRY_BACKOFF_SECONDS | 1 | Inicial backoff для exponential backoff |

### Celery Task Queue
| Переменная | Значение по умолчанию | Назначение |
|------------|----------------------|-----------|
| CELERY_BROKER_URL | redis://localhost:6379/1 | Broker URL для очереди (Redis или RabbitMQ) |
| CELERY_RESULT_BACKEND | redis://localhost:6379/2 | Backend для результатов |
| CELERY_TASK_TRACK_STARTED | true | Отслеживать статус запущенных задач |
| CELERY_TASK_TIME_LIMIT | 3600 | Hard limit для задач в секундах (1 час) |
| CELERY_TASK_SOFT_TIME_LIMIT | 3000 | Soft limit для задач в секундах (50 минут) |

## Особенности

✅ **Pydantic v2 Settings** — современный и типобезопасный подход  
✅ **Модульная структура** — каждая подсистема отдельно  
✅ **Дефолты для локальной разработки** — можно запустить без конфигурации  
✅ **Документированные поля** — каждая переменная имеет описание  
✅ **Заглушки для секретов** — реальные API ключи заполняются вручную  
✅ **Поддержка .env файла** — автоматическая загрузка при наличии `.env`  
✅ **Ленивая загрузка** — глобальный экземпляр создается при первом обращении  

## Использование в коде

```python
from src.weather_alerts.config import get_settings

settings = get_settings()

# Доступ к настройкам
db_url = settings.db.url
redis_url = settings.redis.url
api_port = settings.api.port
weather_key = settings.weather_provider.api_key
```

## Локальная разработка

Скопируй `.env.example` в `.env` и обнови значения:
```bash
cp .env.example .env
# Отредактируй .env с актуальными значениями
```

Зависимости уже в `requirements.txt`:
- pydantic==2.5.0
- pydantic-settings==2.1.0
