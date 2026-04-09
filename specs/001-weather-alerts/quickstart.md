# Быстрый старт: Weather Alerts

## Предварительные требования

- Python 3.11+.
- PostgreSQL 14+.
- Redis 7+.
- Доступ к API weather provider или заглушки ответов провайдера.

## Локальное окружение

1. Создайте и активируйте виртуальное окружение.
2. Установите зависимости проекта.
3. Поднимите PostgreSQL и Redis.
4. Настройте переменные окружения для базы данных, Redis и weather provider.

## Ожидаемые переменные окружения

- `DATABASE_URL`
- `REDIS_URL`
- `WEATHER_PROVIDER_BASE_URL`
- `WEATHER_PROVIDER_API_KEY`
- `EMAIL_PROVIDER_URL`
- `PUSH_PROVIDER_URL`
- `WEBHOOK_DELIVERY_TIMEOUT_SECONDS`

## Запуск сервиса

```bash
python -m uvicorn weather_alerts.api.main:app --reload
```

## Запуск воркеров

```bash
celery -A weather_alerts.workers.celery_app worker --loglevel=info
```

## Запуск тестов

```bash
pytest
```

## Smoke-поток проверки

1. Создайте подписку для одной локации.
2. Добавьте одно или несколько условий с логикой ANY.
3. Подайте подходящее погодное событие.
4. Проверьте, что уведомление отправлено во все активные каналы.
5. Повторно обработайте то же событие и убедитесь, что deduplication блокирует дубли в пределах 12 часов.

## Что проверить перед слиянием

- Работают create/update/disable/enable/delete для подписок.
- Окна расписания корректно учитывают timezone локации.
- Сбой одного канала не блокирует остальные каналы.
- Логи содержат correlation id и итог каждой доставки.
- Проходят unit и integration тесты.