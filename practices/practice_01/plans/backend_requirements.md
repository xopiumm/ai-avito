# Бэкенд-требования: Подписки и Уведомления (WeatherService)

Файл описывает события, API, политику повторных попыток, TTL, SLA и примеры payload для реализации уведомлений.

## 1. Обзор
- Объект: подписки пользователей на погодные уведомления по каналам push/email/sms.
- Основные цели: корректное хранение предпочтений, надежная доставка уведомлений, соблюдение согласий и удобное управление подписками.

## 2. События (Events)
- subscription.created
  - Когда: пользователь завершил подтверждение подписки.
  - Payload: { subscription_id, user_id?, contact, channels, preferences, created_at }
- subscription.updated
  - Когда: пользователь изменил настройки (канал, порог, локации).
- subscription.confirmation_requested
  - Когда: система отправила письмо/SMS с кодом/ссылкой подтверждения.
- notification.scheduled
  - Когда: нотификация запланирована к отправке (правило/cron/trigger).
- notification.dispatched
  - Когда: уведомление передано внешнему провайдеру (provider_id, provider_message_id).
- notification.delivered / notification.failed
  - Когда: доставлено/не доставлено (возможно асинхронно по webhook провайдера).
- notification.retried
  - Когда: выполнена повторная попытка.
- notification.dlq
  - Когда: сообщение ушло в DLQ после исчерпания попыток.

Формат событий: JSON с полями: event_type, event_id, timestamp, payload (object).

## 3. Модель данных (основные поля)
- Subscription
  - subscription_id: UUID
  - user_id: optional (если авторизованный пользователь)
  - contact: { email?, phone?, device_token? }
  - channels: ["email","push","sms"]
  - preferences: { types: ["daily_summary","alert"], thresholds: [...], locales: [...], timezone }
  - status: ["pending","active","failed","unsubscribed"]
  - consent: { accepted_at, source, ip }
  - created_at, updated_at

- NotificationRecord
  - notification_id: UUID
  - subscription_id
  - channel
  - payload (finalized body)
  - provider_id, provider_message_id
  - attempts: int
  - last_error: text
  - status: ["queued","dispatched","delivered","failed","dlq"]
  - created_at, updated_at

## 4. API Endpoints (REST)
- POST /api/v1/subscriptions
  - Описание: создать подписку (initial). Body: { contact, channels, preferences }
  - Response: 201 { subscription_id, status: pending }
  - Security: CSRF/Authentication if required; rate-limit anonymous requests by IP
  - Validation: email/phone format, dedupe by contact+channel

- POST /api/v1/subscriptions/confirm
  - Описание: подтвердить подписку. Body: { subscription_id, token }
  - Response: 200 { subscription_id, status: active }

- GET /api/v1/subscriptions/{id}
  - Получить статус и настройки

- PATCH /api/v1/subscriptions/{id}
  - Обновить preferences/channels

- POST /internal/notifications/trigger
  - Описание: внутренний endpoint для scheduler/rules-engine. Body: { rule_id, target_subscriptions[], context }
  - Response: 202 accepted, возвращает список notification_id
  - Auth: internal token

- POST /hooks/provider/delivery
  - Описание: webhook для получения статусов от внешних провайдеров (email/sms/push)
  - Body: { provider_message_id, status, delivered_at?, error_code?, raw }
  - Response: 200 OK

- GET /internal/metrics/notifications
  - Для дашбордов. Auth internal.

Именование: все операции idempotent где возможно (см. idempotency ниже).

## 5. Политика повторных попыток и DLQ
- Общая логика
  - Retry при временных ошибках (5xx, network errors) по политике exponential backoff.
  - Max attempts: configurable per channel (рекомендуемые значения: email 5, push 3, sms 4).
  - Backoff: exponential с jitter: base=2s, multiplier=2, max_backoff=1h, с рандомизацией ±20%.
  - Non-retryable errors: permanent 4xx (invalid contact), провайдер-спам блокировки.
- DLQ
  - После исчерпания попыток переносить NotificationRecord в DLQ с reason и трассировкой.
  - DLQ должна сохранять метаданные и raw_payload для последственного анализа.

## 6. TTL и хранение
- NotificationRecord TTL: хранить минимум 30 дней для аудита, можно архивировать (cold storage) через 90 дней.
- Subscription contacts retention: хранить пока пользователь не запросил удаление; при запросе удалять или анонимизировать согласно политике.
- Confirmation tokens TTL: 24 часа (настраиваемо).

## 7. SLA / SLI (предложения)
- SLI: Delivery rate per channel = successful_deliveries / attempts (за период)
- SLI: p95 latency = время от notification.scheduled до notification.dispatched
- Целевые показатели (пример, формализовать):
  - Email delivery rate >= 95% (при условии корректных контактов)
  - Push dispatch latency p95 <= 10s
  - SMS delivery rate >= 90%
- SLA: оповещать команду при деградации SLI ниже порога и создавать инцидент.

## 8. Idempotency и дедупликация
- При создании подписки и триггеров использовать idempotency-key (UUID) для предотвращения дублирования.
- Notification pipeline должен проверять дубли по composite key (subscription_id + rule_id + window) для предотврашения спама.

## 9. Observability и метрики
- Собирать метрики:
  - count(subscriptions.created), subscriptions.confirmed, subscriptions.failed
  - notifications.queued, notifications.dispatched, notifications.delivered, notifications.failed, notifications.dlq
  - attempts distribution, avg latency, p95
- Логи: correlational request_id/event_id включать при каждой записи для трейсинга.
- Алерты: рост DLQ, падение delivery_rate, увеличение latency p95.

## 10. Безопасность и соответствие
- Хранение контактов и согласий с шифрованием at-rest.
- Запросы на удаление данных через API (Data Subject Request) и ежедневный отчёт об удалениях.
- Audit logs для всех изменений статуса подписки и отправок уведомлений.
- Обязательное хранение согласия (consent) с метаданными: timestamp, source, ip.

## 11. Примеры payload
- Subscription create
  - Request:
    {
      "contact": { "email": "user@example.com" },
      "channels": ["email"],
      "preferences": { "types": ["daily_summary"], "timezone": "Europe/Moscow" },
      "idempotency_key": "uuid-v4"
    }
  - Response 201:
    { "subscription_id": "uuid", "status": "pending" }

- Notification event (internal)
  {
    "event_type": "notification.scheduled",
    "event_id": "evt-uuid",
    "timestamp": "2026-02-13T07:00:00Z",
    "payload": {
      "notification_id": "notif-uuid",
      "subscription_id": "sub-uuid",
      "channel": "email",
      "body": {
        "title": "Утренний прогноз",
        "text": "Сегодня ожидается дождь, температура +5°C",
        "meta": { "location": "Moscow", "valid_until": "2026-02-13T12:00:00Z" }
      }
    }
  }

- Provider webhook sample
  {
    "provider_message_id": "prov-123",
    "status": "delivered",
    "delivered_at": "2026-02-13T07:01:30Z",
    "raw": { /* provider raw payload */ }
  }

## 12. Acceptance criteria (BDD-like)
- Для Story 1 (подписка email): при POST /subscriptions создается запись, подтверждение отправлено, после подтверждения статус active.
- Для Story 4 (retry/DLQ): при симуляции временных ошибок система делает N попыток, затем message попадает в DLQ и логируется.

## 13. Зависимости и интеграции
- Провайдеры email (SMTP, SendGrid, SES), SMS-провайдеры, push-сервисы (APNs, FCM), очередь сообщений (Kafka/Rabbit/SQS).
- Rules engine / scheduler для триггеров.

## 14. Notes и рекомендации реализации
- Начать с простого pipeline: scheduler -> queue -> dispatcher -> provider.
- Поддерживать idempotency и диагностику (tracing header).
- Реализовать feature flags для каналов и retry-policies для поэтапного релиза.

---

Файл создан как рабочий документ требований для backend-команды. Откройте его: [`plans/backend_requirements.md`](plans/backend_requirements.md:1).