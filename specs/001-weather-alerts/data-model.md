# Модель данных: Weather Alerts

## Сущности

### User

Владелец подписок на погодные уведомления.

**Поля**
- `id`
- `email`
- `timezone`
- `created_at`
- `updated_at`

**Примечание**
- Управление пользователями предполагается в существующей системе; в этой функции используется внешний идентификатор пользователя.

### Location

Нормализованная локация для погодных данных.

**Поля**
- `id`
- `provider_location_key`
- `display_name`
- `latitude`
- `longitude`
- `timezone`
- `created_at`
- `updated_at`

**Ограничения**
- Локация должна быть однозначной.
- Для расписания обязателен timezone.

### Subscription

Одна пользовательская конфигурация оповещений для одной локации.

**Поля**
- `id`
- `user_id`
- `location_id`
- `status` (`active`, `disabled`, `deleted`)
- `condition_mode` (`ANY`)
- `schedule_timezone_source` (`location`)
- `active_from`
- `active_to`
- `created_at`
- `updated_at`
- `deleted_at`

**Связи**
- Принадлежит одному `User`.
- Привязана к одной `Location`.
- Имеет много `SubscriptionCondition`.
- Имеет много `DeliveryChannel`.

### SubscriptionCondition

Одно условие внутри подписки.

**Поля**
- `id`
- `subscription_id`
- `type` (`temperature_below`, `temperature_above`, `rain_probability_above`, `wind_speed_above`, `severe_weather`)
- `threshold_value`
- `threshold_unit`
- `severity_event_type` для `severe_weather`
- `created_at`

**Ограничения**
- Для числовых условий обязателен `threshold_value`.
- Для severe weather обязателен `severity_event_type`.

### DeliveryChannel

Один канал доставки, связанный с подпиской.

**Поля**
- `id`
- `subscription_id`
- `type` (`email`, `push`, `webhook`)
- `destination`
- `active`
- `failure_state`
- `retry_count`
- `last_failure_at`
- `created_at`
- `updated_at`

**Ограничения**
- У подписки должен быть хотя бы один активный канал доставки.

### WeatherEvent

Нормализованное погодное событие для оценки условий.

**Поля**
- `id`
- `location_id`
- `event_type`
- `forecast_date`
- `source_timestamp`
- `payload`
- `created_at`

**Примечание**
- `payload` может храниться в JSON-формате для полей провайдера.

### PendingNotification

Уведомление, отложенное до следующего разрешенного окна доставки.

**Поля**
- `id`
- `subscription_id`
- `weather_event_id`
- `next_delivery_at`
- `status` (`pending`, `released`, `canceled`)
- `created_at`
- `updated_at`

### DeliveryLog

Базовая запись аудита по попытке доставки или ее пропуску.

**Поля**
- `id`
- `subscription_id`
- `delivery_channel_id`
- `weather_event_id`
- `outcome` (`sent`, `failed`, `skipped`, `pending`, `canceled`)
- `attempt_no`
- `error_code`
- `error_message`
- `created_at`

## Обзор связей

- Один `User` имеет много `Subscription`.
- Одна `Location` имеет много `Subscription` и много `WeatherEvent`.
- Одна `Subscription` имеет много `SubscriptionCondition` и `DeliveryChannel`.
- Один `WeatherEvent` может порождать много `DeliveryLog` записей, обычно по одной на канал и попытку.
- Одна `Subscription` может иметь много `PendingNotification`.

## Правила валидации

- Подписка должна ссылаться ровно на одного пользователя и одну локацию.
- Набор условий подписки не может быть пустым.
- `condition_mode` фиксирован в `ANY`.
- Каналы доставки ограничены типами email, push и webhook.
- Расписание должно быть валидно в timezone локации.
- Удаленная подписка не может инициировать новые попытки доставки.

## Стратегия индексов

- Индекс `subscriptions(user_id, status)` для быстрого списка активных подписок пользователя.
- Индекс `subscriptions(location_id, status)` для fanout по событию локации.
- Индекс `delivery_logs(subscription_id, created_at)` для аудита.
- Индекс `pending_notifications(subscription_id, next_delivery_at)` для выпуска pending.
- Дедупликация обеспечивается Redis-ключами с TTL 12 часов, а не только SQL-ограничениями.