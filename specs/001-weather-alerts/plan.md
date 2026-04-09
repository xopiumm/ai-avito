# Технический план реализации: Weather Alerts

**Ветка**: `001-weather-alerts` | **Дата**: 9 апреля 2026 г. | **Спецификация**: [spec.md](spec.md)
**Вход**: Спецификация функции из `/specs/001-weather-alerts/spec.md`

## Краткое резюме

Функция Weather Alerts реализуется как backend-сервис на Python с REST API, PostgreSQL для хранения состояния подписок и журнала доставок, Redis для дедупликации и координации фоновой обработки, а также отдельными адаптерами для внешнего weather provider и каналов доставки email/push/webhook. Ключевая доменная логика выносится в переиспользуемую библиотеку, а CLI добавляется для ручной проверки правил и локальной отладки.

## Технический контекст

**Язык и версия**: Python 3.11+  
**Основные зависимости**: FastAPI, Pydantic v2, SQLAlchemy 2.x, asyncpg, Alembic, Redis 7+, Celery, httpx, pytest, pytest-asyncio, OpenTelemetry  
**Хранилище**: PostgreSQL + Redis  
**Тестирование**: unit + integration + contract tests на pytest/pytest-asyncio  
**Целевая платформа**: Linux backend в контейнерном окружении  
**Тип проекта**: web-service + переиспользуемая core-библиотека + CLI  
**Цели производительности**: первая попытка отправки менее 1 минуты после обнаружения события; идемпотентность; dedup window 12 часов  
**Ограничения**: расписание по timezone локации, только логика ANY внутри подписки, изоляция ошибок каналов, базовый delivery log, отсутствие SMS  
**Масштаб**: большое количество активных подписок, fanout на несколько каналов, горизонтальное масштабирование API и воркеров

## Проверка на соответствие конституции

*GATE: Должен пройти до Phase 0, затем повторная проверка после Phase 1.*

- Приоритет русского языка: pass
- Library-first: pass, доменная логика выделяется в отдельный модуль
- CLI как обязательный интерфейс: pass, предусмотрен CLI для проверки правил
- TDD и высокая покрываемость core-логики: pass
- Фокус на интеграционных тестах: pass

**Итог**: PASS

## Структура проекта

### Документация функции

```text
specs/001-weather-alerts/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── api-contract.md
└── tasks.md
```

### Кодовая структура в репозитории

```text
src/
└── weather_alerts/
    ├── api/
    ├── adapters/
    ├── cli/
    ├── config/
    ├── domain/
    ├── services/
    └── workers/

tests/
├── contract/
├── integration/
└── unit/
```

**Выбранное решение**: Один deployable backend-сервис с переиспользуемой доменной библиотекой и отдельным CLI. PostgreSQL хранит устойчивое состояние и delivery logs, Redis покрывает дедупликацию и координацию фоновых задач.

## Артефакты Phase 0

- [research.md](research.md): выбор стека, стратегии retries и deduplication, observability, риски.

## Артефакты Phase 1

- [data-model.md](data-model.md): сущности, поля, связи, валидации и индексы.
- [contracts/api-contract.md](contracts/api-contract.md): API contracts и внутренние события.
- [quickstart.md](quickstart.md): локальный запуск и smoke-проверка.

## Архитектура компонентов

1. API слой: REST эндпоинты управления подписками и валидация входа.
2. Domain слой: оценка условий, расписания, правил dedup и идемпотентности.
3. Integration adapters: weather provider, email, push, webhook.
4. Worker слой: обработка событий, fanout доставки, retries.
5. Observability слой: структурированные логи, метрики и трассировка.

## Поток событий

1. Weather provider публикует новое погодное событие или прогноз.
2. Событие нормализуется в тип, пригодный для доменных правил.
3. Выбираются активные подписки по локации.
4. Для каждой подписки проверяется набор условий с логикой ANY.
5. Если окно закрыто, создается pending запись.
6. Если окно открыто и dedup не блокирует, запускается fanout по каналам.
7. Каждый канал обрабатывается независимо, с отдельным retry-потоком.
8. Все попытки и результаты фиксируются в delivery log.

## Стратегия retries

- Канало-ориентированная модель: retries независимы для email/push/webhook.
- Временные ошибки (например, timeout или 5xx) обрабатываются через exponential backoff.
- После исчерпания retries канал помечается как failed, но другие каналы продолжают выполнение.

## Стратегия deduplication

- Ключ dedup определяется как user + subscription + channel + weather_event_type.
- Redis хранит ключи с TTL 12 часов.
- Попытка отправки блокируется, если ключ уже активен в dedup window.
- После истечения TTL при повторном выполнении условия отправка снова разрешена.

## Наблюдаемость и эксплуатация

- Структурированные JSON-логи с correlation/trace id.
- Метрики: event-to-first-attempt latency, success/failure rate по каналам, retry exhaustion, dedup hit rate, pending backlog.
- Трассировка: сквозной trace от получения weather event до результата доставки.
- Технические health endpoints для API, worker и интеграций.

## Стратегия тестирования

- Unit tests: условия, расписание, дедупликация, идемпотентность, расчет backoff.
- Integration tests: сценарии Subscription -> Event -> Delivery с реальными PostgreSQL/Redis в тестовом окружении и моками внешних провайдеров.
- Contract tests: валидация схем REST API и внутренних payload для событий.

## Этапы реализации

### Phase 0: Foundation

1. Реализовать доменные модели и правила валидации.
2. Настроить PostgreSQL схему и миграции.
3. Настроить Redis и dedup ключи.

### Phase 1: Delivery Pipeline

1. Реализовать intake погодных событий и движок оценки условий.
2. Реализовать fanout отправки и retry-потоки по каналам.
3. Реализовать pending-логику для закрытого окна доставки.

### Phase 2: Hardening

1. Добавить observability и эксплуатационные метрики.
2. Довести покрытие unit/integration/contract тестами.
3. Подтвердить выполнение NFR по времени первой попытки и надежности.

## Трекинг сложности

Нарушений конституции не зафиксировано, отдельные исключения не требуются.