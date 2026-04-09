# Задачи: Weather Alerts

**Вход**: документы дизайна из [specs/001-weather-alerts](specs/001-weather-alerts)  
**Обязательные источники**: [specs/001-weather-alerts/plan.md](specs/001-weather-alerts/plan.md), [specs/001-weather-alerts/spec.md](specs/001-weather-alerts/spec.md)  
**Дополнительно**: [specs/001-weather-alerts/research.md](specs/001-weather-alerts/research.md), [specs/001-weather-alerts/data-model.md](specs/001-weather-alerts/data-model.md), [specs/001-weather-alerts/contracts/api-contract.md](specs/001-weather-alerts/contracts/api-contract.md), [specs/001-weather-alerts/quickstart.md](specs/001-weather-alerts/quickstart.md)

**Тесты**: обязательны unit + integration по требованиям функции.

## Формат: `[ID] [P?] [Story] Описание`

- `[P]`: задача может выполняться параллельно
- `[Story]`: привязка к пользовательской истории (US1, US2, US3, US4)
- В каждой задаче указан точный путь файла

## Phase 1: Инфраструктурный минимум для MVP

**Цель**: поднять минимальный каркас проекта и окружения, чтобы начать отдельные инженерные коммиты.

- [ ] T001 Создать каркас модулей сервиса в src/weather_alerts/api/__init__.py, src/weather_alerts/domain/__init__.py, src/weather_alerts/services/__init__.py, src/weather_alerts/adapters/__init__.py, src/weather_alerts/workers/__init__.py, src/weather_alerts/cli/__init__.py
- [ ] T002 [P] Добавить базовую конфигурацию окружения в src/weather_alerts/config/settings.py и .env.example
- [ ] T003 [P] Настроить инфраструктуру PostgreSQL и Redis для локального запуска в docker-compose.yml
- [ ] T004 Добавить начальные зависимости и dev-зависимости в requirements.txt

---

## Phase 2: Foundational (блокирующие основы)

**Цель**: подготовить фундамент, который обязателен для всех последующих историй.

**Критично**: без завершения фазы нельзя корректно реализовывать API, оценку погоды и доставку.

- [ ] T005 Реализовать базовое подключение к БД и сессию в src/weather_alerts/config/database.py
- [ ] T006 [P] Реализовать клиент Redis и утилиты ключей в src/weather_alerts/config/redis.py
- [ ] T007 [P] Создать базовые ORM-модели Subscription, SubscriptionCondition, DeliveryChannel в src/weather_alerts/domain/models/subscription.py
- [ ] T008 Создать каркас миграций Alembic в migrations/env.py и migrations/versions/0001_initial_schema.py

**Checkpoint**: фундамент готов, можно начинать пользовательские истории.

---

## Phase 3: User Story 1 - Управление подписками через REST API (Priority: P1) 🎯 MVP

**Goal**: пользователь может создавать, просматривать, обновлять, отключать, включать и удалять подписки.

**Independent Test**: полностью пройти lifecycle подписки через REST API для одного пользователя и двух локаций.

- [ ] T009 [P] [US1] Добавить Pydantic-схемы подписки в src/weather_alerts/api/schemas/subscription.py
- [ ] T010 [US1] Реализовать SubscriptionService с create/list/get/update/disable/enable/delete в src/weather_alerts/services/subscription_service.py
- [ ] T011 [US1] Реализовать REST-роуты подписок в src/weather_alerts/api/routes/subscriptions.py
- [ ] T012 [US1] Подключить роутер и обработку ошибок API в src/weather_alerts/api/main.py

---

## Phase 4: User Story 2 - Weather evaluation (Priority: P1)

**Goal**: система корректно оценивает погодные события и расписание по правилам ANY.

**Independent Test**: на одном weather event проверить all/none/any-match сценарии по условиям и окну расписания.

- [ ] T013 [P] [US2] Реализовать адаптер weather provider в src/weather_alerts/adapters/weather_provider.py
- [ ] T014 [US2] Реализовать движок оценки условий (temperature/rain/wind/severe + ANY) в src/weather_alerts/services/condition_evaluation_service.py
- [ ] T015 [US2] Реализовать проверку окна расписания и timezone-логику в src/weather_alerts/services/schedule_service.py

---

## Phase 5: User Story 3 - Notification pipeline и delivery channels (Priority: P1)

**Goal**: при совпадении условий запускается pipeline доставки во все активные каналы.

**Independent Test**: для одного срабатывания условия получить отдельные результаты по email/push/webhook.

- [ ] T016 [P] [US3] Реализовать notification orchestration entrypoint в src/weather_alerts/services/notification_orchestrator.py
- [ ] T017 [P] [US3] Реализовать email-адаптер доставки в src/weather_alerts/adapters/email_sender.py
- [ ] T018 [P] [US3] Реализовать push-адаптер доставки в src/weather_alerts/adapters/push_sender.py
- [ ] T019 [P] [US3] Реализовать webhook-адаптер доставки в src/weather_alerts/adapters/webhook_sender.py

---

## Phase 6: User Story 4 - Deduplication (Priority: P2)

**Goal**: система блокирует дубли на уровне user+subscription+channel+event_type в окне 12 часов.

**Independent Test**: повторная обработка одинакового события внутри 12 часов не создает новую отправку по каналу.

- [ ] T020 [P] [US4] Реализовать DeduplicationService на Redis TTL=12h в src/weather_alerts/services/deduplication_service.py
- [ ] T021 [US4] Интегрировать dedup-проверку в notification_orchestrator в src/weather_alerts/services/notification_orchestrator.py
- [ ] T022 [US4] Реализовать обработку pending-уведомлений для закрытого окна в src/weather_alerts/services/pending_notification_service.py

---

## Phase 7: Retries

**Цель**: обеспечить надежные повторные попытки с exponential backoff и изоляцией каналов.

- [ ] T023 Реализовать Celery app и очередь задач доставки в src/weather_alerts/workers/celery_app.py
- [ ] T024 Реализовать retry-задачи email/push/webhook с exponential backoff в src/weather_alerts/workers/delivery_tasks.py

---

## Phase 8: Observability

**Цель**: добавить логи, метрики и health-проверки для эксплуатации.

- [ ] T025 [P] Добавить структурированное логирование и correlation id в src/weather_alerts/config/logging.py и src/weather_alerts/api/middleware/request_context.py
- [ ] T026 Добавить метрики и health endpoints в src/weather_alerts/api/routes/health.py и src/weather_alerts/api/routes/metrics.py

---

## Phase 9: Тесты (unit + integration)

**Цель**: подтвердить корректность реализации и целевые NFR.

- [ ] T027 [P] Написать unit-тесты бизнес-правил в tests/unit/test_condition_evaluation_service.py и tests/unit/test_schedule_service.py
- [ ] T028 [P] Написать unit-тесты dedup и retries в tests/unit/test_deduplication_service.py и tests/unit/test_delivery_tasks.py
- [ ] T029 [P] Написать integration-тесты Subscription -> Event -> Delivery в tests/integration/test_subscription_lifecycle.py и tests/integration/test_event_delivery_pipeline.py
- [ ] T030 Написать integration-тесты отказов каналов и pending/retry сценариев в tests/integration/test_channel_isolation_and_pending.py

---

## Phase 10: Polish и финальная проверка

**Цель**: финализировать документацию и подтвердить рабочий end-to-end сценарий.

- [ ] T031 [P] Обновить quickstart и runbook в specs/001-weather-alerts/quickstart.md и README.md
- [ ] T032 Выполнить финальную e2e-проверку по quickstart и зафиксировать результаты в artifacts/report_p1.md

---

## Зависимости и порядок выполнения

### Межфазовые зависимости

- Phase 1 -> Phase 2 -> US1/US2/US3/US4 -> Retries -> Observability -> Tests -> Polish
- US4 зависит от US3, так как dedup и pending встраиваются в pipeline доставки.
- Retries зависят от готовых delivery adapters (US3).
- Tests идут после реализации по вашему требованию, чтобы показать историю коммитов вида spec -> code -> tests.

### Зависимости историй

- **US1 (P1)**: стартует после Foundational, независима от остальных историй.
- **US2 (P1)**: стартует после Foundational, зависит от базовых моделей подписки.
- **US3 (P1)**: стартует после Foundational и US2 (нужна оценка события).
- **US4 (P2)**: стартует после US3 (интеграция в notification pipeline).

### Параллельные возможности

- В Setup: T002 и T003 параллельно.
- В Foundational: T006 и T007 параллельно после T005.
- В US3: T017, T018, T019 параллельно.
- В Tests: T027, T028, T029 параллельно, затем T030.

---

## Пример параллельного запуска (US3)

```bash
# Независимая реализация delivery channels:
Task: "T017 Реализовать email-адаптер в src/weather_alerts/adapters/email_sender.py"
Task: "T018 Реализовать push-адаптер в src/weather_alerts/adapters/push_sender.py"
Task: "T019 Реализовать webhook-адаптер в src/weather_alerts/adapters/webhook_sender.py"
```

---

## Стратегия реализации

### MVP-first

1. Завершить Phase 1 и Phase 2.
2. Реализовать US1 (REST API lifecycle подписок).
3. Проверить MVP вручную и зафиксировать отдельным коммитом.

### Инкрементальная поставка

1. US2 (weather evaluation).
2. US3 (notification pipeline + channels).
3. US4 (dedup + pending).
4. Retries.
5. Observability.
6. Tests.

### Коммит-ритм (мелкие коммиты)

- Делать отдельный коммит на каждую задачу или минимальную логическую пару.
- Последовательность для git log: `spec -> code (по фазам) -> tests -> polish`.

---

## Карточки задач (title, purpose, inputs/dependencies, deliverables, DoD, commit scope)

### T001

- title: Каркас модулей сервиса
- purpose: Зафиксировать базовую структуру проекта для отдельных инкрементальных коммитов.
- inputs / dependencies: plan.md, структура из Technical Context.
- concrete deliverables: Пакеты `api`, `domain`, `services`, `adapters`, `workers`, `cli` с `__init__.py`.
- definition of done: Импорт пакетов не падает, структура соответствует плану.
- suggested commit scope: `src/weather_alerts/**/__init__.py`

### T002

- title: Базовая конфигурация окружения
- purpose: Централизовать параметры приложения и секреты.
- inputs / dependencies: T001.
- concrete deliverables: `settings.py`, `.env.example`.
- definition of done: Конфиг читается из env, есть дефолты для локальной разработки.
- suggested commit scope: `src/weather_alerts/config/settings.py`, `.env.example`

### T003

- title: Локальная инфраструктура PostgreSQL/Redis
- purpose: Обеспечить воспроизводимый локальный запуск.
- inputs / dependencies: T001.
- concrete deliverables: `docker-compose.yml` с сервисами postgres/redis.
- definition of done: Контейнеры запускаются и доступны приложению.
- suggested commit scope: `docker-compose.yml`

### T004

- title: Зависимости проекта
- purpose: Зафиксировать runtime/dev зависимости.
- inputs / dependencies: T001.
- concrete deliverables: Обновленный `requirements.txt`.
- definition of done: Все нужные библиотеки добавлены и устанавливаются.
- suggested commit scope: `requirements.txt`

### T005

- title: Базовое подключение к БД
- purpose: Подготовить слой доступа к PostgreSQL.
- inputs / dependencies: T002, T004.
- concrete deliverables: `database.py` с engine/session factory.
- definition of done: Успешная инициализация сессии по `DATABASE_URL`.
- suggested commit scope: `src/weather_alerts/config/database.py`

### T006

- title: Redis-клиент и утилиты ключей
- purpose: Подготовить общий слой Redis для dedup и очередей.
- inputs / dependencies: T002, T004.
- concrete deliverables: `redis.py` с клиентом и базовыми helper-функциями.
- definition of done: Подключение к Redis работает, ключи формируются централизованно.
- suggested commit scope: `src/weather_alerts/config/redis.py`

### T007

- title: Базовые ORM-модели подписки
- purpose: Зафиксировать основной доменный скелет данных.
- inputs / dependencies: T005.
- concrete deliverables: ORM-модели Subscription, SubscriptionCondition, DeliveryChannel.
- definition of done: Модели валидны для миграций и отражают data-model.md.
- suggested commit scope: `src/weather_alerts/domain/models/subscription.py`

### T008

- title: Начальная миграция схемы
- purpose: Формализовать стартовую схему БД.
- inputs / dependencies: T005, T007.
- concrete deliverables: Alembic env + revision `0001_initial_schema.py`.
- definition of done: Миграция применима на чистой БД.
- suggested commit scope: `migrations/env.py`, `migrations/versions/0001_initial_schema.py`

### T009

- title: API-схемы подписок
- purpose: Стандартизировать request/response модели REST API.
- inputs / dependencies: T007, api-contract.md.
- concrete deliverables: Pydantic-схемы для create/update/read/list.
- definition of done: Схемы соответствуют API contract и валидируют payload.
- suggested commit scope: `src/weather_alerts/api/schemas/subscription.py`

### T010

- title: SubscriptionService
- purpose: Инкапсулировать бизнес-операции жизненного цикла подписки.
- inputs / dependencies: T007, T009.
- concrete deliverables: Реализация CRUD + enable/disable.
- definition of done: Все операции возвращают ожидаемые доменные результаты.
- suggested commit scope: `src/weather_alerts/services/subscription_service.py`

### T011

- title: REST-роуты подписок
- purpose: Открыть API lifecycle подписки наружу.
- inputs / dependencies: T009, T010.
- concrete deliverables: Роуты `/subscriptions*`.
- definition of done: Эндпоинты отвечают по контракту и вызывают сервисный слой.
- suggested commit scope: `src/weather_alerts/api/routes/subscriptions.py`

### T012

- title: Сборка API приложения
- purpose: Подключить роуты и единообразную обработку ошибок.
- inputs / dependencies: T011.
- concrete deliverables: `main.py` с app, routers, handlers.
- definition of done: API стартует и возвращает корректные коды ошибок.
- suggested commit scope: `src/weather_alerts/api/main.py`

### T013

- title: Адаптер weather provider
- purpose: Получать и нормализовать внешние погодные данные.
- inputs / dependencies: T002, T004.
- concrete deliverables: Клиент получения weather events/forecast.
- definition of done: Адаптер возвращает нормализованную структуру для evaluation.
- suggested commit scope: `src/weather_alerts/adapters/weather_provider.py`

### T014

- title: Движок оценки условий
- purpose: Реализовать логику ANY для типов условий из спецификации.
- inputs / dependencies: T007, T013.
- concrete deliverables: Сервис проверки condition set.
- definition of done: Корректно обрабатываются temperature/rain/wind/severe.
- suggested commit scope: `src/weather_alerts/services/condition_evaluation_service.py`

### T015

- title: ScheduleService
- purpose: Применять окна доставки с учетом timezone локации.
- inputs / dependencies: T007, T014.
- concrete deliverables: Сервис проверки доступности окна и next eligible time.
- definition of done: Возвращается корректное решение send-now vs pending.
- suggested commit scope: `src/weather_alerts/services/schedule_service.py`

### T016

- title: Точка входа notification orchestration
- purpose: Собрать единый flow от совпавшего события до fanout доставки.
- inputs / dependencies: T014, T015.
- concrete deliverables: Оркестратор pipeline.
- definition of done: По совпадению условий формируется процесс доставки по каналам.
- suggested commit scope: `src/weather_alerts/services/notification_orchestrator.py`

### T017

- title: Email delivery adapter
- purpose: Добавить отправку уведомлений по email.
- inputs / dependencies: T016.
- concrete deliverables: Адаптер email delivery.
- definition of done: Возвращает стандартизированный результат отправки.
- suggested commit scope: `src/weather_alerts/adapters/email_sender.py`

### T018

- title: Push delivery adapter
- purpose: Добавить отправку уведомлений по push.
- inputs / dependencies: T016.
- concrete deliverables: Адаптер push delivery.
- definition of done: Возвращает стандартизированный результат отправки.
- suggested commit scope: `src/weather_alerts/adapters/push_sender.py`

### T019

- title: Webhook delivery adapter
- purpose: Добавить отправку уведомлений по webhook.
- inputs / dependencies: T016.
- concrete deliverables: Адаптер webhook delivery.
- definition of done: Обрабатывает HTTP-ответы и ошибки транспортного уровня.
- suggested commit scope: `src/weather_alerts/adapters/webhook_sender.py`

### T020

- title: DeduplicationService
- purpose: Блокировать дубли в 12-часовом окне.
- inputs / dependencies: T006, T016.
- concrete deliverables: Redis-based сервис dedup check/set.
- definition of done: Ключи формируются по user+subscription+channel+event_type с TTL 12h.
- suggested commit scope: `src/weather_alerts/services/deduplication_service.py`

### T021

- title: Интеграция dedup в orchestration
- purpose: Встроить dedup gate перед отправкой по каналам.
- inputs / dependencies: T016, T020.
- concrete deliverables: Обновленный orchestration flow с dedup-проверкой.
- definition of done: Повторный event внутри окна не инициирует channel send.
- suggested commit scope: `src/weather_alerts/services/notification_orchestrator.py`

### T022

- title: Pending notification service
- purpose: Реализовать deferred delivery для закрытого окна.
- inputs / dependencies: T015, T016.
- concrete deliverables: Сервис постановки/release/cancel pending.
- definition of done: Pending корректно создается, выпускается и отменяется при удалении подписки.
- suggested commit scope: `src/weather_alerts/services/pending_notification_service.py`

### T023

- title: Celery app
- purpose: Подготовить фоновые очереди для доставки и retries.
- inputs / dependencies: T006, T016.
- concrete deliverables: Инициализация Celery и конфигурация очередей.
- definition of done: Воркеры поднимаются и принимают задачи.
- suggested commit scope: `src/weather_alerts/workers/celery_app.py`

### T024

- title: Retry tasks c exponential backoff
- purpose: Гарантировать повторы временных ошибок и конечный статус failed.
- inputs / dependencies: T017, T018, T019, T023.
- concrete deliverables: Задачи доставки с per-channel retries/backoff.
- definition of done: Timeout/5xx идут в retry, после лимита ставится failed.
- suggested commit scope: `src/weather_alerts/workers/delivery_tasks.py`

### T025

- title: Структурированные логи и correlation id
- purpose: Добавить базовую наблюдаемость по всей цепочке событий.
- inputs / dependencies: T012, T016, T024.
- concrete deliverables: Конфиг логирования + middleware request context.
- definition of done: В логах присутствуют trace/correlation поля.
- suggested commit scope: `src/weather_alerts/config/logging.py`, `src/weather_alerts/api/middleware/request_context.py`

### T026

- title: Метрики и health endpoints
- purpose: Подготовить эксплуатационный контроль API/worker/интеграций.
- inputs / dependencies: T012, T025.
- concrete deliverables: `/health` и `/metrics` роуты.
- definition of done: Эндпоинты возвращают валидный статус и ключевые метрики.
- suggested commit scope: `src/weather_alerts/api/routes/health.py`, `src/weather_alerts/api/routes/metrics.py`

### T027

- title: Unit-тесты evaluation и schedule
- purpose: Подтвердить корректность бизнес-правил условий и окон доставки.
- inputs / dependencies: T014, T015.
- concrete deliverables: Набор unit-тестов для condition/schedule сервисов.
- definition of done: Покрыты позитивные и граничные сценарии.
- suggested commit scope: `tests/unit/test_condition_evaluation_service.py`, `tests/unit/test_schedule_service.py`

### T028

- title: Unit-тесты dedup и retries
- purpose: Защитить критичную логику антидублей и повторных попыток.
- inputs / dependencies: T020, T024.
- concrete deliverables: Unit-тесты dedup сервиса и delivery tasks.
- definition of done: Проверены TTL, skip duplicate, backoff progression, final failed.
- suggested commit scope: `tests/unit/test_deduplication_service.py`, `tests/unit/test_delivery_tasks.py`

### T029

- title: Integration-тесты основного pipeline
- purpose: Проверить путь Subscription -> Event -> Delivery end-to-end.
- inputs / dependencies: T012, T016, T019, T021, T022.
- concrete deliverables: Integration-тесты lifecycle и pipeline.
- definition of done: Сценарии создания подписки и доставки проходят на связке сервисов.
- suggested commit scope: `tests/integration/test_subscription_lifecycle.py`, `tests/integration/test_event_delivery_pipeline.py`

### T030

- title: Integration-тесты отказов и pending/retry
- purpose: Подтвердить изоляцию каналов и корректную отмену/повторы.
- inputs / dependencies: T024, T029.
- concrete deliverables: Интеграционные тесты отказов webhook, pending cancel, retry exhaustion.
- definition of done: Ошибка одного канала не ломает другие; pending/retry обработка соответствует спецификации.
- suggested commit scope: `tests/integration/test_channel_isolation_and_pending.py`

### T031

- title: Обновление документации запуска
- purpose: Синхронизировать quickstart и README с фактической реализацией.
- inputs / dependencies: T026, T030.
- concrete deliverables: Обновленные инструкции запуска и проверки.
- definition of done: По документации можно поднять сервис и пройти smoke flow.
- suggested commit scope: `specs/001-weather-alerts/quickstart.md`, `README.md`

### T032

- title: Финальная e2e-валидация и отчет
- purpose: Зафиксировать результат выполнения плана перед merge.
- inputs / dependencies: T031.
- concrete deliverables: Итоговый отчет с результатами прогонов.
- definition of done: Отчет содержит статус API, pipeline, dedup, retries, observability и тестов.
- suggested commit scope: `artifacts/report_p1.md`

---

## Примечания

- Задачи намеренно мелкие и коммит-ориентированные.
- Структура позволяет показать git log в формате: `spec -> code -> tests`.
- Если команда расширится, [P]-задачи можно распределять параллельно без конфликтов по файлам.