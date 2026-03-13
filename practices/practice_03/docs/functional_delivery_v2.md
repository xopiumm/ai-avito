# Functional Delivery v2.0 — Улучшенные Jira-тикеты WeatherService v1.0

Оценки даны в Story Points (SP). Зависимости указаны как ссылки на тикеты из списка.

---

## SUB-001 — Subscription API и модель данных (PostgreSQL)

**Title:** SUB-001 — Subscription API + PostgreSQL model (CRUD + confirm)

**Description:**
Реализовать базовый REST API для управления подписками и модель данных в PostgreSQL. Включает создание подписки со статусом pending, подтверждение по токену до active, чтение по id, частичное обновление предпочтений/каналов. Обеспечить уникальность подписки и базовую валидацию входных данных.

**Acceptance Criteria (Given/When/Then):**

- **Create subscription (pending):**
  Given валидные email и city и выбран тип уведомления morning
  When клиент вызывает POST /api/v1/subscriptions
  Then создаётся запись в БД со статусом pending, notification_time=morning, и возвращается 201 с subscription_id и статусом pending.
- **Duplicate protection:**
  Given существует подписка с тем же email+city+notification_time
  When клиент повторяет POST /api/v1/subscriptions с теми же данными
  Then возвращается 409 и новая запись в БД не создаётся.
- **Get subscription:**
  Given существует подписка subscription_id
  When клиент вызывает GET /api/v1/subscriptions/{id}
  Then возвращается 200 и данные соответствуют записи в БД.
- **Patch preferences/channels:**
  Given существует подписка active или pending
  When клиент вызывает PATCH /api/v1/subscriptions/{id} с валидными изменениями
  Then возвращается 200, в БД обновляются только разрешённые поля, запрещённые игнорируются/ошибка по контракту.
- **Confirm token changes status:**
  Given существует pending подписка с валидным токеном подтверждения
  When клиент вызывает POST /api/v1/subscriptions/confirm с токеном
  Then возвращается 200, статус становится active, токен становится одноразовым/инвалидируется.

**Test Cases (детально):**
- TC1: POST create → 201; проверить запись в PG (pending, morning, timestamps).
- TC2: POST duplicate → 409; проверить количество записей не изменилось.
- TC3: GET by id → 200; сверить поля с PG.
- TC4: PATCH разрешённых полей → 200; проверить только нужные поля обновились.
- TC5: Confirm валидным токеном → 200; статус active.
- TC6: Confirm повторно тем же токеном → 400/409 (по контракту); статус не меняется.

**Dependencies:**
- Внешние: доступ к PostgreSQL, миграции, секрет для подписи/генерации токенов.

**Priority:** High
**Estimate:** 8 SP

---

## SUB-002 — Email confirmation flow и шаблоны

**Title:** SUB-002 — Email confirmation + resend + unsubscribe link

**Description:**
Добавить отправку email-подтверждения при создании подписки, шаблон письма, endpoint повторной отправки подтверждения, и включить unsubscribe link. Интеграция через адаптер (mockable).

**Acceptance Criteria (Given/When/Then):**

- **Send confirmation on create:**
  Given создана подписка со статусом pending
  When POST /api/v1/subscriptions завершился успешно
  Then отправляется email на адрес подписки с confirmation_link и unsubscribe_link.
- **Confirm via link:**
  Given пользователь переходит по confirmation_link (токен)
  When система принимает токен в POST /api/v1/subscriptions/confirm
  Then подписка становится active, ответ 200.
- **Resend confirmation:**
  Given подписка pending существует
  When клиент вызывает POST /api/v1/subscriptions/{id}/resend-confirmation
  Then отправляется новое письмо подтверждения, ответ 202 (или 200 по контракту).
- **No resend for active:**
  Given подписка active
  When вызывается resend endpoint
  Then возвращается 409 (или 400) и письмо не отправляется.

**Test Cases (детально):**
- TC1: Создать подписку → перехватить письмо (mock provider) → проверить наличие ссылок и токена.
- TC2: Перейти по confirmation → статус в PG active.
- TC3: Resend для pending → письмо отправлено повторно, лимит/троттлинг соблюдён.
- TC4: Resend для active → ошибка, письмо не отправлено.
- TC5: Письмо содержит unsubscribe URL с корректной структурой.

**Dependencies:** SUB-001, email провайдер / mock, шаблоны (plans/notification_templates.md)

**Priority:** High
**Estimate:** 5 SP

---

## SUB-003 — Push интеграция (FCM/APNs)

**Title:** SUB-003 — Push channel: device token registration + test push + delivery status webhook

**Description:**
Реализовать push-канал: регистрацию device_token, отправку тестового push, обработку статусов доставки. Данные хранить в БД, адаптер провайдера — заменяемый.

**Acceptance Criteria (Given/When/Then):**

- **Register device token:**
  Given авторизованный клиент
  When вызывает endpoint регистрации device_token
  Then токен сохраняется и возвращается 200/201.
- **Send test push:**
  Given для подписки есть активный device_token
  When клиент вызывает endpoint test push
  Then провайдер вызывается, создаётся запись NotificationRecord, ответ 202.
- **Delivery status update:**
  Given провайдер присылает статус delivered/failed
  When webhook обработан
  Then NotificationRecord обновлён корректно.

**Test Cases (детально):**
- TC1: Register token → проверить запись в PG.
- TC2: Test push → проверить вызов адаптера провайдера и NotificationRecord.
- TC3: Webhook delivered → статус NotificationRecord=delivered.
- TC4: Webhook failed → last_error заполнен, attempts не растут.

**Dependencies:** SUB-001, SUB-005

**Priority:** Low
**Estimate:** 8 SP

---

## SUB-004 — SMS для критических предупреждений

**Title:** SUB-004 — SMS channel: phone add + verification + send alerts

**Description:**
Добавить SMS как канал для критических алертов: сбор номера, верификация кодом, отправка сообщений, учёт статусов и попыток.

**Acceptance Criteria (Given/When/Then):**

- **Add phone + start verification:**
  Given пользователь вводит номер телефона
  When вызывает endpoint добавления номера
  Then создаётся verification challenge и отправляется SMS с кодом.
- **Confirm phone:**
  Given пользователь вводит корректный код
  When вызывает endpoint подтверждения
  Then номер помечается verified и доступен для alerts.
- **Send alert SMS:**
  Given алерт сработал и канал SMS включён
  When диспетчер отправляет SMS
  Then создаётся NotificationRecord, статус отражает результат.

**Test Cases (детально):**
- TC1: Add phone → mock provider получил SMS с кодом.
- TC2: Confirm корректным кодом → phone verified.
- TC3: Trigger alert → NotificationRecord создан, попытки и статусы корректны.
- TC4: Provider fail → retry/DLQ (если используется общий pipeline).

**Dependencies:** SUB-005, провайдер SMS + региональные требования

**Priority:** Low
**Estimate:** 13 SP

---

## SUB-005 — Delivery Pipeline: Dispatcher, Retry и DLQ

**Title:** SUB-005 — Notification delivery pipeline: queue → dispatcher → provider adapters + retry/DLQ

**Description:**
Построить delivery pipeline для уведомлений: очередь (EventBus), воркеры-диспетчеры, адаптеры провайдеров. Реализовать retry policy (exponential backoff), DLQ и идемпотентность.

**Acceptance Criteria (Given/When/Then):**

- **Enqueue:**
  Given создано событие notification.scheduled
  When событие публикуется в очередь
  Then оно доступно для обработки dispatcher-ом.
- **Dispatch success path:**
  Given сообщение в очереди и провайдер доступен
  When dispatcher обрабатывает сообщение
  Then провайдер вызывается 1 раз, создаётся/обновляется NotificationRecord.
- **Retry on transient failure:**
  Given провайдер возвращает 5xx/timeout
  When dispatcher получает ошибку
  Then выполняются ретраи по конфигу, attempts увеличивается, сохраняется last_error.
- **DLQ on exhausted retries:**
  Given ретраи исчерпаны
  When последняя попытка неуспешна
  Then сообщение попадает в DLQ, NotificationRecord помечается failed.
- **Idempotency:**
  Given повторное сообщение с тем же idempotency key
  When dispatcher обрабатывает повтор
  Then дубликат отправки не выполняется, запись не дублируется.

**Test Cases (детально):**
- TC1: enqueue → dispatcher → provider called → NotificationRecord updated.
- TC2: provider 5xx → N retries → verify backoff scheduling.
- TC3: after N retries → DLQ contains message, NotificationRecord=failed.
- TC4: duplicate idempotency key → only one provider call.

**Dependencies:** Решение по EventBus (Kafka/Rabbit/SQS), SUB-007

**Priority:** Medium
**Estimate:** 13 SP

---

## SUB-006 — Rules Engine и триггеры (cron/threshold)

**Title:** SUB-006 — Rules engine: daily cron (morning digest) + threshold triggers → emits notification.scheduled

**Description:**
Реализовать правила генерации событий уведомлений: cron для ежедневной утренней сводки и threshold-правила. Генерировать события в очередь.

**Acceptance Criteria (Given/When/Then):**

- **Create cron rule:**
  Given подписка active с типом morning
  When время соответствует cron-правилу
  Then генерируется notification.scheduled для этой подписки.
- **Bind rule to subscription/location:**
  Given подписка привязана к city
  When правило срабатывает
  Then событие содержит нормализованную локацию и ссылку на subscription_id.
- **Threshold rule:**
  Given задан threshold (например wind_speed > X)
  When входные данные погоды удовлетворяют условию
  Then событие генерируется один раз по правилам дедупликации.

**Test Cases (детально):**
- TC1: Cron rule → "время наступило" → событие опубликовано.
- TC2: Проверить payload события: subscription_id, city, type, idempotency key.
- TC3: Threshold rule → mock weather → событие есть/нет по условию.

**Dependencies:** SUB-001, SUB-005, Доступ к cron runner (APScheduler/Cloud scheduler)

**Priority:** Medium
**Estimate:** 8 SP

---

## SUB-007 — Observability: метрики, логи, алерты

**Title:** SUB-007 — Observability for subscriptions & notifications: metrics + dashboards + alerts + tracing IDs

**Description:**
Добавить наблюдаемость: метрики API (latency, error rate), метрики доставки (delivery_rate, attempts, DLQ), корреляция request_id/event_id, алерты. Настроить дашборды в staging/prod.

**Acceptance Criteria (Given/When/Then):**

- **Metrics emitted:**
  Given обработка POST /subscriptions и POST /confirm
  When запросы выполняются
  Then публикуются метрики latency p50/p95, status codes, error rate.
- **Delivery metrics:**
  Given dispatcher отправляет уведомления
  When выполняются attempts/retries/DLQ
  Then метрики attempts, success/fail, DLQ count обновляются.
- **Alerts configured:**
  Given delivery_rate падает ниже порога или DLQ растёт
  When выполняются условия
  Then алерт срабатывает.
- **Traceability:**
  Given есть request_id/event_id
  When ищем запись в логах/трейсах
  Then можно связать API request → событие → попытки доставки.

**Test Cases (детально):**
- TC1: Прогнать тестовый запрос → проверить наличие метрик endpoint-а.
- TC2: Симулировать DLQ spike → проверить алерт/правило.
- TC3: Проверить корреляцию: request_id присутствует в логах API и dispatcher.

**Dependencies:** SUB-005, Prometheus/Grafana/APM

**Priority:** Medium
**Estimate:** 5 SP

---

## SUB-008 — Compliance, Consent и DSR

**Title:** SUB-008 — Consent + DSR (delete/anonymize) + audit log for subscriptions

**Description:**
Обеспечить хранение согласия (consent), реализацию DSR (удаление/анонимизация), и аудит-лог всех изменений статуса подписки.

**Acceptance Criteria (Given/When/Then):**

- **Consent stored on create:**
  Given пользователь создаёт подписку
  When POST /subscriptions успешен
  Then consent сохраняется с timestamp и source, доступен для аудита.
- **DSR request:**
  Given существует подписка по email
  When подан DSR на удаление/анонимизацию
  Then контактные данные удалены/анонимизированы, подписка деактивирована, audit log записан.
- **Audit log:**
  Given происходит изменение статуса (pending→active, unsubscribe, dsr)
  When изменение применяется
  Then создаётся audit запись с actor/source и временем.

**Test Cases (детально):**
- TC1: Create subscription → consent record exists with correct fields.
- TC2: Confirm → audit log has status change entry.
- TC3: DSR → PII удалено/заменено, подписка не активна, audit log есть.
- TC4: Повторный DSR → идемпотентное поведение (200/204), без ошибок/дубликатов.

**Dependencies:** SUB-001, Legal/GDPR согласование

**Priority:** High
**Estimate:** 8 SP

---

## Сводка зависимостей и приоритетов

| Приоритет | Тикеты | Обоснование |
|---|---|---|
| High | SUB-001 → SUB-002 → SUB-008 | Ядро email-подписки + комплаенс |
| Medium | SUB-006, SUB-007, SUB-005 | Cron для утренней сводки, observability, надёжная доставка |
| Low | SUB-003, SUB-004 | Каналы push/sms — расширения |

**MVP v1.0 (только email-сводка):** SUB-001, SUB-002, SUB-006, SUB-008, SUB-007 (перед продом).
