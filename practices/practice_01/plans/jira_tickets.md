# Jira tickets (8) — WeatherService: Подписки и Уведомления

Ниже 8 тикетов, готовых для импорта в Jira. Каждый тикет содержит Title, Description, Acceptance Criteria, Test cases и Dependencies/Notes.

---

1) Title: SUB-001 — Subscription API и модель данных
Description:
  Разработать REST API для создания, подтверждения, получения и обновления подписок. Реализовать модель Subscription в Postgres с полями contact, channels, preferences, consent, status.
Acceptance Criteria:
  - POST /api/v1/subscriptions создает запись со статусом pending
  - POST /api/v1/subscriptions/confirm переводит статус в active при валидном токене
  - GET /api/v1/subscriptions/{id} возвращает корректные данные
  - PATCH /api/v1/subscriptions/{id} обновляет preferences и channels
Test cases:
  - TC: создать подписку с валидным email -> проверить pending запись
  - TC: подтвердить подписку по токену -> статус active
  - TC: обновить каналы -> проверки в БД
Dependencies/Notes:
  - Зависит от: доступ к Postgres, секреты для генерации токенов
  - Design: UX-макеты подписки (см. [`plans/cjm.md`](plans/cjm.md:1))

---

2) Title: SUB-002 — Email confirmation flow и шаблоны
Description:
  Реализовать отправку email-подтверждений при создании подписки, шаблоны письма и endpoint для повторной отправки подтверждения.
Acceptance Criteria:
  - Письмо с confirmation_link отправляется при создании подписки
  - confirmation_link ведёт на API, где POST /subscriptions/confirm принимает токен
  - В письме есть unsubscribe-link
Test cases:
  - TC: создать подписку -> проверить отправку email (mock/провайдер)
  - TC: ссылка подтверждения переводит подписку в active
  - TC: письмо содержит unsubscribe ссылку
Dependencies/Notes:
  - Интеграция с провайдером email (SendGrid/SES)
  - Требуется шаблоны i18n (см. [`plans/notification_templates.md`](plans/notification_templates.md:1))

---

3) Title: SUB-003 — Push интеграция (FCM / APNs)
Description:
  Поддержать push-уведомления: регистрацию device_token, отправку тестового уведомления и обработку статусов доставки.
Acceptance Criteria:
  - UI/endpoint для регистрации device_token реализован
  - Тестовое push-уведомление доставляется при нажатии кнопки
  - Webhook/статусы провайдера корректно обрабатываются
Test cases:
  - TC: зарегистрировать device_token -> отправить test push -> проверить dispatched
  - TC: симуляция провайдера returning delivered/failed -> проверить обновление NotificationRecord
Dependencies/Notes:
  - Нужны ключи FCM/APNs и настройка push adapter
  - Обратить внимание на platform-specific permission flows

---

4) Title: SUB-004 — SMS для критических предупреждений
Description:
  Добавить канал SMS для критических предупреждений: форма добавления номера, верификация (код/SMS) и интеграция с SMS-провайдером.
Acceptance Criteria:
  - Пользователь может добавить номер телефона и выбрать SMS для alerts
  - При срабатывании alert генерируется SMS и отправляется провайдеру
  - Логируются статусы отправки и попытки
Test cases:
  - TC: добавить номер -> получить код подтверждения -> подтвердить
  - TC: при trigger alert -> проверить запись в NotificationRecord и попытки отправки
  - TC: симуляция failed -> retry и DLQ поведение
Dependencies/Notes:
  - Интеграция с локальным или глобальным SMS провайдером (Twilio и т.п.)
  - Региональные ограничения и стоимость

---

5) Title: SUB-005 — Delivery Pipeline: Dispatcher, Retry и DLQ
Description:
  Построить pipeline: EventBus (queue) -> Dispatcher workers -> Provider adapters; реализовать retry policy (exponential backoff) и DLQ.
Acceptance Criteria:
  - Notifications от scheduler/rules попадают в очередь
  - Dispatcher пытается отправить, повторяет по конфигу и помещает в DLQ при исчерпании попыток
  - NotificationRecord хранит attempts, last_error и provider_message_id
Test cases:
  - TC: enqueue notification -> dispatcher обрабатывает -> provider получает request
  - TC: симуляция 5xx -> multiple retries -> после N попыток запись в DLQ
  - TC: idempotency: повторный enqueue с тем же idempotency-key не создает дубликата
Dependencies/Notes:
  - Требуется выбор EventBus (Kafka/Rabbit/SQS)
  - Инструментирование tracing/metrics

---

6) Title: SUB-006 — Rules Engine и триггеры (cron/threshold)
Description:
  Реализовать rules engine для scheduled и threshold-based триггеров, экспортировать событие notification.scheduled в очередь.
Acceptance Criteria:
  - Можно создать правило: cron (daily_summary) и threshold (например wind_speed > X)
  - При наступлении условия генерируется event notification.scheduled
  - Rules могут быть привязаны к локациям и подпискам
Test cases:
  - TC: создать cron-rule -> проверить generation of events в ожидаемое время
  - TC: создать threshold-rule -> отправить mock-weather-event -> проверить генерацию notification
Dependencies/Notes:
  - Возможно выделенный сервис rules-engine или использование существующего scheduler

---

7) Title: SUB-007 — Observability, метрики и алерты
Description:
  Настроить сбор метрик и дашборды: delivery_rate, attempts, p95 dispatch latency, DLQ count; настроить алерты при деградации.
Acceptance Criteria:
  - Есть дашборд с ключевыми SLI/SLAs
  - Настроены алерты: drop in delivery_rate, DLQ spike, p95 latency > threshold
  - События трассируются через pipeline (request_id/event_id)
Test cases:
  - TC: сымитировать падение delivery_rate -> проверить, что alert сработал
  - TC: проверить наличие трассы по request_id в логах для заданного notification_id
Dependencies/Notes:
  - Интеграция с Prometheus/Grafana или облачной APM

---

8) Title: SUB-008 — Compliance, Consent и DSR
Description:
  Обеспечить хранение согласий (consent), реализацию процесса DSR (удаление/анонимизация), audit-log всех изменений статуса подписки.
Acceptance Criteria:
  - Consent сохраняется при создании подписки с timestamp и source
  - Есть API для подачи DSR и удаления/анонимизации контакта
  - Audit-log сохраняет все изменения статусов и запросы на удаление
Test cases:
  - TC: создать подписку с consent -> проверить запись consent
  - TC: выполнить DSR -> проверить удаление/анонимизацию и audit-log
Dependencies/Notes:
  - Согласовать с legal/GDPR командой формат хранения и retention policy

---

Файл сохранён как [`plans/jira_tickets.md`](plans/jira_tickets.md:1).