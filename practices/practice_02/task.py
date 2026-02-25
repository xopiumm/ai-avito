import json
import os
from typing import List

"""
ПРАКТИКА 2: ПРОФЕССИОНАЛЬНЫЙ ПРОМПТИНГ (R.C.T.F.)
Курс: AI-инструменты в жизни инженера (ИТМО)

ИНСТРУКЦИЯ:
В этой практике мы учимся не просто "болтать" с AI, а программировать его поведение
с помощью фреймворка R.C.T.F. (Role, Context, Task, Format).
"""

# =================================================================================================
# 1. ИНФОРМАЦИЯ
# =================================================================================================
STUDENT_INFO = {
    "full_name": "Дима Милана Вячеславовна",
    "group_number": "M3305",
    "date": "2026-02-20"
}

# =================================================================================================
# 2. ЖУРНАЛ R.C.T.F. (Самая важная часть!)
# =================================================================================================
class RCTF_Log:
    def __init__(self, task_name: str, role: str, context: str, task: str, format_instruction: str, result: str):
        self.task_name = task_name
        self.role = role             # R: Кто такой AI? (Senior QA, Architect...)
        self.context = context       # C: Контекст проекта (Веб-сервис, Python, FastAPI...)
        self.task = task             # T: Что конкретно сделать?
        self.format = format_instruction # F: В каком виде выдать ответ? (Markdown, Gherkin...)
        self.result = result         # Итог (кратко)

PROMPT_LOGS: List[RCTF_Log] = [
    RCTF_Log(
        task_name="Mermaid Diagram v2",
        role="Senior DevOps Architect с опытом проектирования микросервисных систем",
        context="Мы проектируем сервис 'WeatherService' — REST API для уведомлений о погоде. Текущие компоненты: 1. FastAPI Backend (REST API) 2. PostgreSQL Database (подписки пользователей) 3. OpenWeatherMap API (данные о погоде) 4. Client Apps (веб/мобильные приложения) Технологический стек: - Backend: Python (FastAPI) - База данных: PostgreSQL - Внешний API: OpenWeatherMap (REST) - Client Apps: Веб/мобильные приложения Новое требование: добавить Redis для кэширования данных о погоде.",
        task="Модифицируй нашу базовую архитектуру: 1. Добавь Redis как компонент кэширования данных о погоде 2. Укажи протоколы взаимодействия между компонентами (REST, HTTP) 3. Добавь Rate Limiter для защиты API",
        format_instruction="Сгенерируй Mermaid диаграмму компонентов. Требования к схеме: - Используй формат `graph TB` или `graph LR` - Для каждого компонента добавь краткое описание в квадратных скобках - Укажи протоколы на связях (например: \"|REST API|\") - Используй разные формы для разных типов компонентов ([] для сервисов, (()) для БД, {} для внешних API)",
        result="Сгенерировал обновленную диаграмму"
    ),
    RCTF_Log(
        task_name="Gherkin Scenarios",
        role="опытный QA Automation Engineer с 8-летним опытом в написании автоматизированных тестов для веб-сервисов и ботов.",
        context="У нас есть User Story: Подписка на утреннюю сводку (v1.0) - Как пользователь, я хочу подписаться на ежедневную утреннюю сводку по email для моей локации, чтобы получать краткий прогноз перед выходом из дома. - Acceptance criteria: - Есть кнопка подписки в UI прогноза. - Форма собирает email и тип уведомления (утренняя сводка). - На email отправляется письмо подтверждения с ссылкой. - После подтверждения у пользователя появляется запись в БД подписок. Технический контекст: - Система: REST API на Python (FastAPI) - API погоды: OpenWeatherMap - База данных: PostgreSQL (хранит: email, city, notification_time) - Кэширование: Redis (кэш данных о погоде с TTL 10 минут) Пользовательский флоу через API: 1. Клиент отправляет POST /subscribe с {city, email} 2. API проверяет существование города через OpenWeatherMap 3. API сохраняет подписку в PostgreSQL 4. API возвращает подтверждение с данными о погоде",
        task="Acceptance Criteria:	•	В UI прогноза есть кнопка «Подписаться на утреннюю сводку».	•	В форме подписки собираются: email и тип уведомления (утренняя сводка).	•	При POST /subscribe с {city, email} система проверяет город через OpenWeatherMap.	•	Если город валиден — создаётся подписка в PostgreSQL (email, city, notification_time=утро) и возвращаются данные о погоде.	•	Пользователю отправляется письмо подтверждения со ссылкой; после перехода по ссылке подписка становится активной.	•	Дубликат подписки (тот же email+city) не создаётся (возвращается ошибка).	•	Несуществующий город отклоняется (возвращается ошибка), запись в БД не создаётся.•	Город с лишними пробелами/спецсимволами корректно обрабатывается (нормализуется) или отклоняется, если OpenWeatherMap не распознаёт.	•	Данные погоды кэшируются в Redis на 10 минут.",
        format_instruction="Используй строгий Gherkin-синтаксис (Given/When/Then). Cтруктура:Scenario 1: [Название позитивного сценария]  Given [предусловие]  When [действие] Then [ожидаемый результат]   And [дополнительная проверка] Scenario 2: [Название негативного сценария] аналогично Требования: - Минимум 2 позитивных сценария - Минимум 2 негативных сценария (несуществующий город, дубликат подписки) - 1 граничный случай (город с пробелами/спецсимволами) - Итого: минимум 5 сценариев",
        result="Сгенерировал 6 сценариев в формате Gherkin"
    ),
    RCTF_Log(
        task_name="DoR v2.0",
        role="Product Owner с 5-летним опытом в Agile/Scrum",
        context="Мы разрабатываем WeatherService — REST API для уведомлений о погоде. Наш текущий Definition of Ready v1.0: 1. User story и Acceptance Criteria - Полное описание user story и минимум 2–3 acceptance criteria в Gherkin-стиле (Given/When/Then). - Критерии включают проверку создания подписки, подтверждения, доставки и обработки ошибок. 2. UX/Copy и дизайн-артефакты - Финальные макеты экранов/модалей для подписки, подтверждения и управления подписками. - Текст писем/SMS и i18n-ключи готовы. Включены примеры CTA и fallback-тексты для недостающих полей. 3. API / Events контракт и payload samples - Описаны REST-эндпоинты и внутренние события (см. plans/backend_requirements.md), включены примеры request/response и webhook payloads. - Назначен владелец контракта (API owner). 4. Инфраструктурные зависимости и конфигурация - Указаны провайдеры (email/SMS/push), очередь сообщений, quota и credentials; есть доступы/секреты в vault или инструкция для их получения. - Наличие feature-flag для поэтапного включения канала/ретраев. 5. Observability и тестовые данные - Список метрик/дэшбордов (delivery_rate, p95 latency, DLQ count) и критерии тревоги. - Подготовлены тестовые контакты/токены и план для e2e тестов (включая симуляцию ошибок провайдера). 6. Соответствие и безопасность - Модель согласий (consent) определена и хранение контактов соответствует политике конфиденциальности. - Определён процесс обработки DSR (удаление/анонимизация) и требования по шифрованию. Проблемы v1.0: - Слишком общий - Нет структуры по категориям - Нет специфики для REST API проекта",
        task="Создай улучшенную версию Definition of Ready v2.0.",
        format_instruction="Структурированный чек-лист в Markdown с категориями: - Requirements (требования к задаче) - Technical (технические аспекты) - Design (дизайн API/контракты) - Testing (тестирование) - Documentation (документация) Каждая категория должна содержать 3-5 конкретных пунктов.",
        result="Сгенерировал структурированный чек-лист DoR v2.0"
    ),
    RCTF_Log(
        task_name="DoD v2.0",
        role="Scrum Master с опытом в DevOps и CI/CD.",
        context="""Мы разрабатываем WeatherService — REST API для уведомлений о погоде.
Наш текущий Definition of Done v1.0:
DoD (Definition of Done) — Подписки и Уведомления (WeatherService)
Список из 5 пунктов, необходимых для пометки фичи как готовой к релизу.
1. Feature implemented и покрытие тестами
   - Backend: unit tests для логики подписок/диспетчера и интеграционные тесты для retry/DLQ.
   - Frontend: e2e-скрипт для подписки/подтверждения и тестового уведомления.
2. API и контракты задокументированы
   - OpenAPI/Swagger для публичных endpoint`ов и примеры payload для внутренних событий.
   - Подписаны контрактные поля с командами-потребителями (API owner).
3. Observability и алерты настроены
   - Дашборд с ключевыми метриками (delivery_rate, p95 latency, DLQ count) в prod/staging.
   - Алерты при порогах (drop in delivery_rate, DLQ spike).
4. Compliance и безопасность
   - Consent хранится и доступен для аудита; DSR-адаптер протестирован.
   - Все секреты и провайдерские ключи хранятся в Vault, доступные роли задокументированы.
5. Документация и handoff
   - Обновлён CJM и roadmap in plans/cjm.md.
   - Передача команде QA и разработчикам: checklist тест-кейсов и agenda для handoff-meeting.
Проблемы v1.0:
- Недостаточно деталей
- Нет структуры
- Нет специфики для REST API""",
        task="Создай улучшенную версию Definition of Done v2.0.",
        format_instruction="""Структурированный чек-лист в Markdown с категориями:
- Code (код)
- Tests (тесты)
- Documentation (документация)
- Review (код-ревью)
- Deployment (деплой)
Каждая категория должна содержать 3-5 конкретных пунктов.""",
        result="Сгенерировал структурированный чек-лист DoD v2.0"
    ),
    RCTF_Log(
        task_name="Test Plan v2.0",
        role="Test Lead с 10-летним опытом в тестировании Python-приложений и микросервисов.Test Lead с 10-летним опытом в тестировании Python-приложений и микросервисов.",
        context="""Мы готовимся к тестированию User Story:
Подписка на утреннюю сводку (v1.0)
   - Как пользователь, я хочу подписаться на ежедневную утреннюю сводку по email для моей локации, чтобы получать краткий прогноз перед выходом из дома.
   - Acceptance criteria:
     - Есть кнопка подписки в UI прогноза.
     - Форма собирает email и тип уведомления (утренняя сводка).
     - На email отправляется письмо подтверждения с ссылкой.
     - После подтверждения у пользователя появляется запись в БД подписок.
Компоненты системы для тестирования:
graph TB
  %% Clients
  WEB[Web Client App<br/>UI for managing subscriptions & viewing forecasts]
  MOB[Mobile Client App<br/>UI for managing subscriptions & viewing forecasts]
  %% Edge / Protection
  RL[Rate Limiter<br/>Protects API from abuse & enforces quotas]
  %% Core service
  API[FastAPI WeatherService<br/>REST API: subscriptions, forecasts, notifications]
  %% Data stores
  PG((PostgreSQL DB<br/>Stores users, subscriptions, notification settings))
  REDIS((Redis Cache<br/>Caches weather responses by city/coords + TTL))
  %% External dependency
  OWM{OpenWeatherMap API<br/>External weather provider}
Технологии тестирования:
- Unit: pytest, pytest-asyncio
- Integration: pytest, testcontainers (для Redis, PostgreSQL)
- E2E: pytest, httpx (тестирование HTTP endpoints)""",
        task="Создай комплексный план тестирования для этой фичи. Включи тесты на всех уровнях: unit, integration, end-to-end.",
        format_instruction="""Markdown-таблица со следующими колонками:
| ID | Тип | Компонент | Описание | Предусловия | Шаги | Ожидаемый результат |
Требования:
- Минимум 12 тест-кейсов
- Распределение: ~50% unit, ~30% integration, ~20% e2e
- ID формата: TC-001, TC-002, ...
- Тип: Unit/Integration/E2E
- Покрыть позитивные, негативные и граничные случаи""",
        result="Сгенерировал 20 тест-кейсов, распределённых по уровням тестирования"
    ),
    RCTF_Log(
        task_name="Functional Delivery v2.0",
        role="Senior Delivery Manager с опытом в Agile и управлении бэклогом.",
        context="У нас есть базовые Jira-тикеты для WeatherService v1.0:"
                " Jira tickets (8) — WeatherService: Подписки и Уведомления"
                "Ниже 8 тикетов, готовых для импорта в Jira. Каждый тикет содержит Title, Description, Acceptance Criteria, Test cases и Dependencies/Notes."
                "---"
                "1) Title: SUB-001 — Subscription API и модель данных"
                "Description:"
                "  Разработать REST API для создания, подтверждения, получения и обновления подписок. Реализовать модель Subscription в Postgres с полями contact, channels, preferences, consent, status."
                "Acceptance Criteria:"
                "  - POST /api/v1/subscriptions создает запись со статусом pending"
                "  - POST /api/v1/subscriptions/confirm переводит статус в active при валидном токене"
                "  - GET /api/v1/subscriptions/{id} возвращает корректные данные"
                "  - PATCH /api/v1/subscriptions/{id} обновляет preferences и channels"
                "Test cases:"
                "  - TC: создать подписку с валидным email -> проверить pending запись"
                "  - TC: подтвердить подписку по токену -> статус active"
                "  - TC: обновить каналы -> проверки в БД"
                "Dependencies/Notes:"
                "  - Зависит от: доступ к Postgres, секреты для генерации токенов"
                "  - Design: UX-макеты подписки (см. [plans/cjm.md](plans/cjm.md:1))"
                "---"
                "2) Title: SUB-002 — Email confirmation flow и шаблоны"
                "Description:"
                "  Реализовать отправку email-подтверждений при создании подписки, шаблоны письма и endpoint для повторной отправки подтверждения."
                "Acceptance Criteria:"
                "  - Письмо с confirmation_link отправляется при создании подписки"
                "  - confirmation_link ведёт на API, где POST /subscriptions/confirm принимает токен"
                "  - В письме есть unsubscribe-link"
                "Test cases:"
                "  - TC: создать подписку -> проверить отправку email (mock/провайдер)"
                "  - TC: ссылка подтверждения переводит подписку в active"
                "  - TC: письмо содержит unsubscribe ссылку"
                "Dependencies/Notes:"
                "  - Интеграция с провайдером email (SendGrid/SES)"
                "  - Требуется шаблоны i18n (см. [plans/notification_templates.md](plans/notification_templates.md:1))"
                "---"
                "3) Title: SUB-003 — Push интеграция (FCM / APNs)"
                "Description:"
                "  Поддержать push-уведомления: регистрацию device_token, отправку тестового уведомления и обработку статусов доставки."
                "Acceptance Criteria:"
                "  - UI/endpoint для регистрации device_token реализован"
                "  - Тестовое push-уведомление доставляется при нажатии кнопки"
                "  - Webhook/статусы провайдера корректно обрабатываются"
                "Test cases:"
                "  - TC: зарегистрировать device_token -> отправить test push -> проверить dispatched"
                "  - TC: симуляция провайдера returning delivered/failed -> проверить обновление NotificationRecord"
                "Dependencies/Notes:"
                "  - Нужны ключи FCM/APNs и настройка push adapter"
                "  - Обратить внимание на platform-specific permission flows"
                "---"
                "4) Title: SUB-004 — SMS для критических предупреждений"
                "Description:"
                "  Добавить канал SMS для критических предупреждений: форма добавления номера, верификация (код/SMS) и интеграция с SMS-провайдером."
                "Acceptance Criteria:"
                "  - Пользователь может добавить номер телефона и выбрать SMS для alerts"
                "  - При срабатывании alert генерируется SMS и отправляется провайдеру"
                "  - Логируются статусы отправки и попытки"
                "Test cases:"
                "  - TC: добавить номер -> получить код подтверждения -> подтвердить"
                "  - TC: при trigger alert -> проверить запись в NotificationRecord и попытки отправки"
                "  - TC: симуляция failed -> retry и DLQ поведение"
                "Dependencies/Notes:"
                "  - Интеграция с локальным или глобальным SMS провайдером (Twilio и т.п.)"
                "  - Региональные ограничения и стоимость"
                "---"
                "5) Title: SUB-005 — Delivery Pipeline: Dispatcher, Retry и DLQ"
                "Description:"
                "  Построить pipeline: EventBus (queue) -> Dispatcher workers -> Provider adapters; реализовать retry policy (exponential backoff) и DLQ."
                "Acceptance Criteria:"
                "  - Notifications от scheduler/rules попадают в очередь"
                "  - Dispatcher пытается отправить, повторяет по конфигу и помещает в DLQ при исчерпании попыток"
                "  - NotificationRecord хранит attempts, last_error и provider_message_id"
                "Test cases:"
                "  - TC: enqueue notification -> dispatcher обрабатывает -> provider получает request"
                "  - TC: симуляция 5xx -> multiple retries -> после N попыток запись в DLQ"
                "  - TC: idempotency: повторный enqueue с тем же idempotency-key не создает дубликата"
                "Dependencies/Notes:"
                "  - Требуется выбор EventBus (Kafka/Rabbit/SQS)"
                "  - Инструментирование tracing/metrics"
                "---"
                "6) Title: SUB-006 — Rules Engine и триггеры (cron/threshold)"
                "Description:"
                "  Реализовать rules engine для scheduled и threshold-based триггеров, экспортировать событие notification.scheduled в очередь."
                "Acceptance Criteria:"
                "  - Можно создать правило: cron (daily_summary) и threshold (например wind_speed > X)"
                "  - При наступлении условия генерируется event notification.scheduled"
                "  - Rules могут быть привязаны к локациям и подпискам"
                "Test cases:"
                "  - TC: создать cron-rule -> проверить generation of events в ожидаемое время"
                "  - TC: создать threshold-rule -> отправить mock-weather-event -> проверить генерацию notification"
                "Dependencies/Notes:"
                "  - Возможно выделенный сервис rules-engine или использование существующего scheduler"
                "---"
                "7) Title: SUB-007 — Observability, метрики и алерты"
                "Description:"
                "  Настроить сбор метрик и дашборды: delivery_rate, attempts, p95 dispatch latency, DLQ count; настроить алерты при деградации."
                "Acceptance Criteria:"
                "  - Есть дашборд с ключевыми SLI/SLAs"
                "  - Настроены алерты: drop in delivery_rate, DLQ spike, p95 latency > threshold"
                "  - События трассируются через pipeline (request_id/event_id)"
                "Test cases:"
                "  - TC: сымитировать падение delivery_rate -> проверить, что alert сработал"
                "  - TC: проверить наличие трассы по request_id в логах для заданного notification_id"
                "Dependencies/Notes:"
                "  - Интеграция с Prometheus/Grafana или облачной APM"
                "---"
                "8) Title: SUB-008 — Compliance, Consent и DSR"
                "Description:"
                "  Обеспечить хранение согласий (consent), реализацию процесса DSR (удаление/анонимизация), audit-log всех изменений статуса подписки."
                "Acceptance Criteria:"
                "  - Consent сохраняется при создании подписки с timestamp и source"
                "  - Есть API для подачи DSR и удаления/анонимизации контакта"
                "  - Audit-log сохраняет все изменения статусов и запросы на удаление"
                "Test cases:"
                "  - TC: создать подписку с consent -> проверить запись consent"
                "  - TC: выполнить DSR -> проверить удаление/анонимизацию и audit-log"
                "Dependencies/Notes:"
                "  - Согласовать с legal/GDPR командой формат хранения и retention policy"
                "---"
                "Проблемы текущих тикетов:"
                "- Недостаточно детальные Acceptance Criteria"
                "- Нет зависимостей между тикетами"
                "- Нет приоритетов"
                "- Нет оценок времени"
                "- Тест-кейсы слишком общие",
        task="Улучши эти тикеты до профессионального уровня.",
        format_instruction="Структурированный список тикетов в Markdown. Каждый тикет должен содержать: - Title (название) - Description (описание задачи) - Acceptance Criteria (детальные в формате Given/When/Then) - Test Cases (детальные тест-кейсы) - Dependencies (зависимости от других тикетов) - Priority (High/Medium/Low) - Estimate (story points или часы)",
        result="Сгенерировал улучшенные Jira-тикеты"
    ),
    RCTF_Log(
        task_name="hw Event Storming 2.0",
        role="Действуй как Senior Product Manager с 8 летним опытом в коммерческой разработке",
        context="""
        Мы проектируем Weather Service REST API для уведомлений о погоде. Ранее мы записали результат нашего Event Storming
Actors

End User (Web/Mobile) — управляет подписками через REST API, получает in-app/push/email уведомления
External Weather API (Provider) — даёт прогнозы/алерты; источник WeatherForecastUpdated
Scheduler / Orchestrator — планировщик задач (cron, cloud scheduler) вызывает RefreshForecast и запускает периодические jobs
Delivery Worker / Notification Service — отвечает за ProcessNotificationQueue и интеграцию с внешними каналами (FCM/APNs, SMTP, Telegram Bot API)
Дополнительный актор: Telegram Bot (опционально) — двунаправленный: принимает Subscribe/Unsubscribe и доставляет сообщения
Commands

SubscribeToCity От кого: клиент (web/mobile) или Bot Что делает: создаёт подписку и эмитит UserSubscribedToCity Параметры: user_id, city_id, channels, preferences Ответ: subscription_id / error

UnsubscribeFromCity От кого: клиент / Bot Что делает: помечает подписку неактивной и эмитит UserUnsubscribedFromCity Параметры: user_id, city_id, channels(optional)

RefreshForecast От кого: scheduler / operator Что делает: запрашивает прогноз у внешнего Weather API для указанного набора городов; эмитит WeatherForecastUpdated Параметры: city_id(s) or batch, provider_id, force_flag

SendNotification / ProcessNotificationQueue От кого: delivery worker / orchestration Что делает: берёт NotificationScheduled из очереди и пытается доставить по каналам; эмитит NotificationDelivered или NotificationFailed Параметры: notification_id, attempt_number

Domain Events

UserSubscribedToCity Поля: user_id, city_id, channels [telegram,push,email,in-app], preferences {thresholds,quiet_hours}, created_at, source Источник: REST API (клиент web/mobile), Telegram Bot Последствия: создать запись подписки в БД; опубликовать событие для воркера ScheduleNotification Проверки: валидность user_id и city_id, права доступа, дублирующая подписка

UserUnsubscribedFromCity Поля: user_id, city_id, channels_removed, removed_at, source Источник: REST API / Bot Последствия: снять подписку в БД; отменить запланированные уведомления; логировать изменение Проверки: наличие активной подписки, подтверждение владельца

WeatherForecastUpdated Поля: city_id, provider_id, fetched_at, forecast_version, forecast_summary, forecast_payload (raw JSON), ttl Источник: интеграция с внешним Weather API (periodic pull / webhook) Последствия: сохранить snapshot прогноза; запустить правила сравнения (diff) для генерации Alarm/Alert событий; обновить кеш Проверки: подпись/валидность ответа провайдера, таймстемп, процент недостающих полей

WeatherAlertTriggered Поля: alert_id, city_id, alert_type (heavy_rain,storm,temp_drop,frost), severity, observed_at, details, trigger_reason Источник: правило сравнения (внутренний сервис) при получении WeatherForecastUpdated или по push от провайдера Последствия: создать NotificationScheduled для подписанных пользователей; создать Audit запись Проверки: соответствие порогам пользователя, окно тихих часов, дублирование одного алерта

NotificationScheduled Поля: notification_id, user_id, city_id, channels, scheduled_at, payload_summary, status (scheduled) Источник: генератор уведомлений (в ответ на WeatherAlertTriggered или по расписанию) Последствия: поместить задачу в очередь доставки (broker); отслеживать статус доставки Проверки: доступность каналов доставки для user_id, формат payload

NotificationDelivered / NotificationFailed Поля: notification_id, user_id, channel, delivered_at / failed_at, provider_msg_id, error_code, retry_count Источник: delivery worker / внешний push/email/telegram provider Последствия: обновить статус, при ошибке запустить retry или пометить permanent-failure; метрики и алерты на SLA Проверки: id совпадает, таймстемп в пределах ожиданий
        """,
        task="Проанализируй Actors, Commands и Domain Events. Создай улучшенную версию файла",
        format_instruction="Раздели ответ на блоки Actors, Commands и Domain Events, для каждого пункта пиши подробные объяснения ",
        result="Сгенерирован обновленный файл результат Event Storming"
    ),
    RCTF_Log(
        task_name="hw Roadmap 2.0",
        role="Действуй как Senior Product Manager с 8 летним опытом в коммерческой разработке",
        context="""
        Мы проектируем Weather Service REST API для уведомлений о погоде. У нас уже подготовлена первая версия Roadmap
Roadmap: версии и обоснование

v1.0 — Minimum Lovable Product (MLP)

Что включено:
Базовая подписка через email и push (в приложении)
Простая форма подписки (email + выбор типа уведомлений: ежедневная сводка / предупреждения)
Подтверждение email (ссылка)
Отправка базовых уведомлений: утренняя сводка и предупреждение о сильной погоде
Метрики: подтверждения подписки, доставляемость email, CTR уведомлений
Почему:
Быстрая проверка спроса и ценности уведомлений при минимальном объёме разработки
Email и встроенные push покрывают большинство пользователей без сложных интеграций
v1.1 — Улучшение качества доставки и управление подпиской

Что включено:
Добавление SMS как опционального канала для критических предупреждений (при интеграции провайдера)
Тестовое уведомление и индикатор статуса подписки
Простейшая панель управления подписками в профиле (вкл/выкл, выбор каналов)
Retry policy для пушей и email, мониторинг задержек
Почему:
Повышение надежности и доверия пользователей (тестовое уведомление, статус)
SMS — важен для критических оповещений и тех, кто не пользуется приложением
v2.0 — Персонализация и расширенные сценарии

Что включено:
Гибкие правила триггеров (custom thresholds по ветру/осадкам/температуре)
Геофенсинг и уведомления по привязанным локациям
Rich notifications: картинка, CTA, период действия, подробная карточка риска
История уведомлений и аналитика пользовательских реакций
SLA/SLI формализация: целевые показатели доставки и latency
Почему:
Создание высокой ценности для удержания пользователей через персонализированные и релевантные нотификации
Подготовка платформы для коммерческих возможностей (премиум-функции, таргетированные советы)
        """,
        task="Детализируй версии, улучши их и добавь метрики успеха для каждой версии",
        format_instruction="Выведи подробное описание, раздели ответ по версиям ",
        result="Сгенерирована обновленная версия Roadmap 2.0",
    ),
]

# =================================================================================================
# 3. АРТЕФАКТЫ (Улучшенные версии из Практики 1)
# =================================================================================================

# Задание 1: Улучшенная Архитектура (Mermaid v2)
MERMAID_V2 = """
graph TB
  %% Clients
  WEB[Web Client App<br/>UI for managing subscriptions & viewing forecasts]
  MOB[Mobile Client App<br/>UI for managing subscriptions & viewing forecasts]

  %% Edge / Protection
  RL[Rate Limiter<br/>Protects API from abuse & enforces quotas]

  %% Core service
  API[FastAPI WeatherService<br/>REST API: subscriptions, forecasts, notifications]

  %% Data stores
  PG((PostgreSQL DB<br/>Stores users, subscriptions, notification settings))
  REDIS((Redis Cache<br/>Caches weather responses by city/coords + TTL))

  %% External dependency
  OWM{OpenWeatherMap API<br/>External weather provider}

  %% Flows
  WEB -->|HTTPS REST| RL
  MOB -->|HTTPS REST| RL

  RL -->|HTTPS REST| API

  API -->|SQL over TCP| PG

  %% Cache-aside pattern
  API -->|RESP/Redis TCP| REDIS
  REDIS -->|RESP/Redis TCP| API

  API -->|HTTPS REST| OWM
  OWM -->|HTTPS JSON| API

  %% Notes: cache fill path is implicit: miss -> OWM -> API -> REDIS (set with TTL) -> respond
"""

# Задание 2: Gherkin Scenarios (BDD)
GHERKIN_SCENARIOS = """
Feature: Morning email digest subscription v1.0

  Background:
    Given the WeatherService API is running
    And PostgreSQL is available and the subscriptions table is empty for test emails
    And Redis is available and empty for keys related to test cities
    And OpenWeatherMap API is reachable for city validation

  Scenario 1: Create morning digest subscription for a valid city and return weather data (happy path)
    Given a user has entered email "user1@example.com" and selected notification type "morning digest" in the subscription form
    And the user has chosen city "Helsinki"
    When the client sends POST "/subscribe" with JSON:
    {"city":"Helsinki","email":"user1@example.com"}
    Then the response status code should be 201
    And the response body should include "city" = "Helsinki"
    And the response body should include weather data fields
    And a subscription record should be created in PostgreSQL with:
      | email             | city     | notification_time | status   |
      | user1@example.com | Helsinki | morning           | pending  |
    And a confirmation email should be sent to "user1@example.com" containing a confirmation link

  Scenario 2: Confirm subscription via email link and activate it
    Given an existing pending subscription in PostgreSQL for:
      | email             | city     | notification_time | status  |
      | user2@example.com | Tallinn  | morning           | pending |
    And a confirmation token exists for "user2@example.com" and city "Tallinn"
    When the user opens the confirmation link for that token
    Then the response status code should be 200
    And the subscription record in PostgreSQL should be updated to status "active"
    And the user should see a confirmation message that the subscription is activated

  Scenario 3: Weather data is cached in Redis for 10 minutes after subscription
    Given the city "Oslo" is valid in OpenWeatherMap
    And there is no Redis cache entry for city "Oslo"
    When the client sends POST "/subscribe" with JSON:
      {"city":"Oslo","email":"user3@example.com"}
    Then the response status code should be 201
    And Redis should contain a cache entry for city "Oslo" with TTL of 600 seconds
    And the cached value should contain weather data matching the response body

  Scenario 4: Reject subscription when city does not exist (negative)
    Given a user has entered email "user4@example.com" and selected notification type "morning digest" in the subscription form
    And the user has chosen city "NoSuchCity_12345"
    When the client sends POST "/subscribe" with JSON:
      {"city":"NoSuchCity_12345","email":"user4@example.com"}
    Then the response status code should be 400
    And the response body should include an error message about invalid or unknown city
    And no subscription record should be created in PostgreSQL for email "user4@example.com" and city "NoSuchCity_12345"
    And no confirmation email should be sent to "user4@example.com"

  Scenario 5: Reject duplicate subscription for same email and city (negative)
    Given an existing subscription in PostgreSQL for:
      | email             | city     | notification_time | status |
      | user5@example.com | Riga     | morning           | active |
    When the client sends POST "/subscribe" with JSON:
      {"city":"Riga","email":"user5@example.com"}
    Then the response status code should be 409
    And the response body should include an error message about duplicate subscription
    And no additional subscription record should be created in PostgreSQL for email "user5@example.com" and city "Riga"
    And no confirmation email should be sent to "user5@example.com"

  Scenario 6: Handle city input with extra spaces and special symbols (boundary)
    Given a user has entered email "user6@example.com" and selected notification type "morning digest" in the subscription form
    And the user has chosen city "  São   Paulo!!!  "
    When the client sends POST "/subscribe" with JSON:
      {"city":"  São   Paulo!!!  ","email":"user6@example.com"}
    Then the system should normalize the city input or reject it based on OpenWeatherMap recognition
    And if OpenWeatherMap recognizes the normalized city then:
      | expected_status |
      | 201            |
    And a subscription record should be created in PostgreSQL with city equal to the normalized value and status "pending"
    And a confirmation email should be sent to "user6@example.com"
    And if OpenWeatherMap does not recognize the normalized city then:
      | expected_status |
      | 400            |
    And no subscription record should be created in PostgreSQL for email "user6@example.com"
    And no confirmation email should be sent to "user6@example.com"
"""

# Задание 3: Улучшенные DoR и DoD v2.0
DOR_V2 = """
DoR v2.0 — WeatherService (REST API: Подписки и Уведомления)

Requirements
	•	User Story сформулирована в формате роль → потребность → ценность, указан бизнес-контекст (для кого, когда, зачем).
	•	Acceptance Criteria: минимум 3 пункта, включая 1 позитивный и 1 негативный кейс; критерии проверяемы (Given/When/Then).
	•	Определены правила идемпотентности/дубликатов (например, уникальность email+city+type) и ожидаемые ошибки.
	•	Определены ограничения и правила: таймзона, время уведомления “утро”, формат email/города, лимиты подписок на пользователя (если есть).
	•	Понятны зависимости и границы: что делаем в этой задаче, что явно не делаем (out of scope).

Technical
	•	Определены зависимости: OpenWeatherMap (проверка города), PostgreSQL (подписки), Redis (кэш погоды TTL=10 мин), Email-провайдер (подтверждение).
	•	Есть требования к отказоустойчивости: таймауты/ретраи/обработка деградации (например, OWM недоступен → ошибка/фоллбек).
	•	Определены нефункциональные требования: целевые SLO/латентность, лимиты запросов, ожидаемая нагрузка, rate limiting стратегия.
	•	Описана модель данных и миграции: поля (email, city, notification_time, status, token, timestamps), индексы/уникальные ключи.
	•	Определены требования к безопасности: валидация входных данных, защита токенов подтверждения, хранение секретов (env/vault).

Design (дизайн API/контракты)
	•	Эндпоинты описаны и согласованы (минимум): POST /subscribe, GET/POST /confirm (или эквивалент) — с назначением и статус-кодами.
	•	Контракт request/response зафиксирован: обязательные поля, типы, примеры payload, формат ошибок (единый error schema).
	•	Определены правила нормализации city (trim, collapse spaces, допустимые символы) и ожидаемое поведение при нераспознавании OWM.
	•	Описан кэш-паттерн (cache-aside): ключи, TTL=600s, что кэшируем (weather response), когда инвалидируем/обновляем.
	•	Зафиксирована стратегия идемпотентности: заголовок/ключ (Idempotency-Key) или уникальные ограничения + поведение при повторном запросе.

Testing
	•	Есть список тестов уровня API: happy path, несуществующий город, дубликат подписки, подтверждение подписки, валидация входных данных.
	•	Определены моки/стабы: OpenWeatherMap (валидный/невалидный город), email-провайдер (перехват письма/линка), Redis (TTL проверка).
	•	Определены проверки БД: создание записи pending, переход в active после подтверждения, отсутствие записи при ошибках.
	•	Определены проверки кэша: запись в Redis и TTL ≈ 600s, повторное использование кэша (при повторных запросах/в рамках задачи — если применимо).
	•	Согласованы критерии “готово протестировано”: где прогоняются тесты (CI), какие окружения, минимальный набор regression.

Documentation
	•	Обновлён OpenAPI/Swagger: описания эндпоинтов, схемы, примеры, коды ошибок.
	•	Добавлено описание бизнес-флоу подписки: pending → email confirm → active, включая исключения и повторные попытки.
	•	Описаны настройки и конфиги: переменные окружения, ключи OWM, Redis/DB, параметры TTL/таймаутов/лимитов.
	•	Описаны observability-аспекты: ключевые метрики (подписки создано, confirm rate, email send failures, cache hit rate), логи/трейсы.
	•	Добавлены заметки по эксплуатации: rate limiting правила, ограничения внешнего API, диагностика типовых ошибок.
"""

DOD_V2 = """
DoD v2.0 — WeatherService (REST API: Подписки и Уведомления)

Code (код)
	•	Реализованы все AC из user story: подписка POST /subscribe, подтверждение, статусы (pending → active), обработка ошибок.
	•	Валидация и нормализация входных данных (email, city) реализованы и консистентны во всех путях выполнения.
	•	Идемпотентность/антидубликаты обеспечены (уникальный ключ email+city+type или эквивалент), поведение при повторе документировано в коде.
	•	Интеграция с Redis выполнена (TTL=600s), исключения/фоллбеки при недоступности Redis обработаны (без падения сервиса).
	•	Логи и метрики добавлены для ключевых шагов (subscribe, confirm, email send, cache hit/miss, OWM errors) без утечек PII/секретов.

Tests (тесты)
	•	Unit-тесты покрывают: нормализацию city, валидацию email, антидубликаты, генерацию/проверку токена подтверждения, переход статусов.
	•	Интеграционные тесты покрывают: PostgreSQL запись/уникальность, Redis cache set + TTL≈600s, взаимодействие с mock OpenWeatherMap.
	•	Негативные тесты: несуществующий город, дубликат подписки, некорректный email, истёкший/невалидный token подтверждения.
	•	Контрактные тесты/проверки схем: соответствие OpenAPI (request/response/error schema), стабильность кодов ошибок (400/409/5xx).
	•	Тесты запускаются в CI и стабильны (без флейков): детерминированные моки, фиксированные таймауты, изоляция данных.

Documentation (документация)
	•	OpenAPI/Swagger обновлён: эндпоинты, схемы, примеры, статусы, формат ошибок (единый error schema).
	•	Описан флоу подписки: pending → email confirm → active, включая повторные клики по ссылке и ошибки.
	•	Документированы настройки: env-переменные (OWM key, DB, Redis), TTL кэша, таймауты, rate limiting параметры.
	•	Добавлены эксплуатационные заметки: ключевые метрики/алерты, как диагностировать типовые сбои (OWM/Redis/email).
	•	Обновлены миграции/схема данных: поля, индексы, уникальные ограничения; указана стратегия отката.

Review (код-ревью)
	•	Минимум 1–2 аппрува от команды (включая владельца компонента), все комментарии закрыты или отложены с явным решением.
	•	Проверены security-пункты: нет логирования токенов/секретов, корректные HTTP статусы, защита от инъекций, ограничения по входным данным.
	•	Проверены архитектурные решения: кэш-паттерн, обработка деградации (OWM/Redis/email), согласованная стратегия идемпотентности.
	•	Выполнены статические проверки: линтеры/форматтеры, type checks (если используются), dependency scan (если включён в пайплайн).
	•	Согласованы изменения контрактов с потребителями (если есть): версия/обратная совместимость/депрекейшн.

Deployment (деплой)
	•	CI/CD пайплайн зелёный: сборка, тесты, проверки качества, сборка образа, публикация артефактов.
	•	Миграции применяются автоматически/по процедуре и протестированы на staging; есть понятный rollback plan.
	•	Конфигурация окружений обновлена: секреты в vault/secret store, значения TTL=600s, настройки rate limiter.
	•	Деплой в staging выполнен и подтверждён smoke-тестами: /health, /subscribe, /confirm (с моками или тестовыми провайдерами).
	•	Наблюдаемость включена: дашборды/алерты активны, базовые SLO (например, p95 latency, error rate) в норме после релиза.
"""

# Задание 4: Тест-план v2 (Классифицированный)
TEST_PLAN_V2 = """
| ID | Тип | Компонент | Описание | Предусловия | Шаги | Ожидаемый результат |
|---|---|---|---|---|---|---|
| TC-001 | Unit | API | Валидация email: корректный формат принимается | Нет | 1) Вызвать валидатор email с `user@example.com` | Валидатор возвращает OK, ошибок нет |
| TC-002 | Unit | API | Валидация email: некорректный формат отклоняется | Нет | 1) Вызвать валидатор email с `user@@example` | Возвращается ошибка валидации |
| TC-003 | Unit | API | Нормализация city: trim + схлопывание пробелов | Нет | 1) Нормализовать `"  New   York  "` | Результат `"New York"` |
| TC-004 | Unit | API | Нормализация city: обработка спецсимволов (политика: удалить/оставить/отклонить) | Определена политика нормализации | 1) Нормализовать `"São   Paulo!!!"` | Либо спецсимволы удалены/экранированы согласно политике, либо возвращена ошибка нормализации (детерминированно) |
| TC-005 | Unit | API | Логика антидубликата: повторная подписка `email+city+type` вызывает ошибку | Репозиторий/DAO замокан: “существует запись” | 1) Вызвать сервис `create_subscription(email, city, morning)` | Возвращается доменная ошибка “duplicate” (мапится в 409) |
| TC-006 | Unit | API | Установка значений по умолчанию: `notification_time=morning`, `status=pending` | Нет | 1) Создать subscription model из входных `{email, city}` | Поля проставлены корректно (`morning`, `pending`) |
| TC-007 | Unit | API | Генерация токена подтверждения: уникальность и срок жизни | Конфиг TTL токена задан | 1) Сгенерировать 2 токена 2) Проверить формат/длину 3) Проверить наличие exp/TTL | Токены различаются, валидный формат, TTL/exp задан |
| TC-008 | Unit | API | Верификация токена: валидный токен активирует подписку | Репозиторий замокан: запись `pending` существует | 1) Вызвать `confirm_subscription(token)` | Возвращается success, статус меняется на `active` (в слое домена) |
| TC-009 | Unit | API | Верификация токена: истёкший/невалидный токен отклоняется | Репозиторий/крипто-валидатор замокан | 1) Вызвать `confirm_subscription(expired_token)` | Возвращается доменная ошибка “invalid/expired” (мапится в 400/404 по контракту) |
| TC-010 | Unit | API | Cache-aside: при cache miss вызывается OWM-клиент и результат готов к записи в Redis | Redis-клиент и OWM-клиент замоканы | 1) Запросить weather для city с пустым кэшем 2) Проверить вызовы | Был вызов OWM, сформирован payload для cache set с TTL=600 |
| TC-011 | Unit | RL | Rate limiting: превышение лимита приводит к отказу | Модуль RL сконфигурирован (лимит N) | 1) Эмулировать N+1 запросов от одного ключа/клиента | N запросов разрешены, N+1 отклонён (например, 429) |
| TC-012 | Integration | API + PG | Создание подписки записывает `pending` в PostgreSQL и возвращает 201 | testcontainers: PostgreSQL поднят, миграции применены; OWM замокан как валидный | 1) POST `/subscribe` `{city,email}` 2) SELECT из subscriptions | HTTP 201, в БД 1 запись с `email, city(normalized), notification_time=morning, status=pending` |
| TC-013 | Integration | API + PG | Дубликат подписки не создаётся (уникальный индекс/логика) | PostgreSQL поднят; есть существующая запись | 1) Создать подписку 2) Повторить POST теми же `{city,email}` | Второй запрос возвращает 409, в БД по-прежнему 1 запись |
| TC-014 | Integration | API + Redis | Кэш погоды создаётся в Redis с TTL≈600 после `/subscribe` | Redis поднят; OWM замокан валидный; для ключа кэша пусто | 1) POST `/subscribe` 2) Проверить Redis key 3) Проверить TTL | Redis key существует, TTL в диапазоне около 600 секунд, значение соответствует структуре weather |
| TC-015 | Integration | API + OWM(mock) | Несуществующий город отклоняется и не пишет в БД | PostgreSQL поднят; OWM mock возвращает “not found” | 1) POST `/subscribe` с несуществующим city 2) SELECT из БД | HTTP 400, в БД нет записи, в Redis нет кэша, email не отправлен |
| TC-016 | Integration | API + Mailer(mock) + PG | Письмо подтверждения отправляется и содержит ссылку с токеном | PostgreSQL поднят; mailer заглушка/spy включена; OWM валиден | 1) POST `/subscribe` 2) Перехватить письмо 3) Проверить содержимое | Письмо отправлено 1 раз, содержит URL с токеном, в БД статус `pending` и токен сохранён/связан |
| TC-017 | E2E | WEB/UI + API + PG | UI: кнопка “Подписаться на утреннюю сводку” открывает форму и отправляет запрос | E2E окружение доступно; UI развернут; backend доступен | 1) Открыть экран прогноза 2) Нажать кнопку 3) Ввести email 4) Выбрать “утренняя сводка” 5) Submit | Кнопка видна, форма валидируется, отправляется запрос, UI показывает успешное состояние/сообщение |
| TC-018 | E2E | API + PG + Mailer(mock) | Полный флоу: subscribe → получение ссылки → confirm → статус active | Mailer mock перехватывает письма; PG/Redis подняты; OWM валиден | 1) POST `/subscribe` 2) Извлечь confirm link из письма 3) Перейти по ссылке/вызвать `/confirm` 4) Проверить БД | Subscribe возвращает 201, confirm возвращает 200, в БД статус `active` для этой подписки |
| TC-019 | E2E | API + RL | Rate limiter: серия запросов к `/subscribe` блокируется после лимита | RL включён и настроен для тестового ключа/IP | 1) Отправить серию POST `/subscribe` (N+1) с различными email | До лимита ответы успешны/валидны, затем 429 (или согласованный код), сервис остаётся доступным |
| TC-020 | E2E | API + Redis | Повторный запрос на подписку для другого email использует кэш погоды (если применимо) | Redis пуст; OWM mock считает вызовы; city один и тот же | 1) POST `/subscribe` для `userA` 2) POST `/subscribe` для `userB` с тем же city в течение 10 мин 3) Проверить счётчик OWM | Второй запрос возвращает погоду без дополнительного вызова OWM (cache hit), TTL не превышает 600 секунд |
"""

# Задание 5: Улучшенный Functional Delivery v2.0
FUNCTIONAL_DELIVERY_V2 = """
Улучшенные Jira-тикеты — WeatherService v1.0 (Подписки и уведомления)

Оценки даны в Story Points (SP). Зависимости указаны как ссылки на тикеты из списка.

⸻

SUB-001 — Subscription API и модель данных (PostgreSQL)

Title: SUB-001 — Subscription API + PostgreSQL model (CRUD + confirm)

Description:
Реализовать базовый REST API для управления подписками и модель данных в PostgreSQL. Включает создание подписки со статусом pending, подтверждение по токену до active, чтение по id, частичное обновление предпочтений/каналов. Обеспечить уникальность подписки и базовую валидацию входных данных.

Acceptance Criteria (Given/When/Then):
	•	Create subscription (pending):
Given валидные email и city и выбран тип уведомления morning
When клиент вызывает POST /api/v1/subscriptions
Then создаётся запись в БД со статусом pending, notification_time=morning, и возвращается 201 с subscription_id и статусом pending.
	•	Duplicate protection:
Given существует подписка с тем же email+city+notification_time
When клиент повторяет POST /api/v1/subscriptions с теми же данными
Then возвращается 409 и новая запись в БД не создаётся.
	•	Get subscription:
Given существует подписка subscription_id
When клиент вызывает GET /api/v1/subscriptions/{id}
Then возвращается 200 и данные соответствуют записи в БД.
	•	Patch preferences/channels:
Given существует подписка active или pending
When клиент вызывает PATCH /api/v1/subscriptions/{id} с валидными изменениями
Then возвращается 200, в БД обновляются только разрешённые поля, запрещённые игнорируются/ошибка по контракту.
	•	Confirm token changes status:
Given существует pending подписка с валидным токеном подтверждения
When клиент вызывает POST /api/v1/subscriptions/confirm с токеном
Then возвращается 200, статус становится active, токен становится одноразовым/инвалидируется.

Test Cases (детально):
	•	TC1: POST create → 201; проверить запись в PG (pending, morning, timestamps).
	•	TC2: POST duplicate → 409; проверить количество записей не изменилось.
	•	TC3: GET by id → 200; сверить поля с PG.
	•	TC4: PATCH разрешённых полей → 200; проверить только нужные поля обновились.
	•	TC5: Confirm валидным токеном → 200; статус active.
	•	TC6: Confirm повторно тем же токеном → 400/409 (по контракту); статус не меняется.

Dependencies:
	•	Внешние: доступ к PostgreSQL, миграции, секрет для подписи/генерации токенов.

Priority: High
Estimate: 8 SP

⸻

SUB-002 — Email confirmation flow и шаблоны

Title: SUB-002 — Email confirmation + resend + unsubscribe link

Description:
Добавить отправку email-подтверждения при создании подписки, шаблон письма, endpoint повторной отправки подтверждения, и включить unsubscribe link (как минимум как заготовку/контракт). Интеграция через адаптер (mockable).

Acceptance Criteria (Given/When/Then):
	•	Send confirmation on create:
Given создана подписка со статусом pending
When POST /api/v1/subscriptions завершился успешно
Then отправляется email на адрес подписки с confirmation_link и unsubscribe_link.
	•	Confirm via link:
Given пользователь переходит по confirmation_link (токен)
When система принимает токен в POST /api/v1/subscriptions/confirm
Then подписка становится active, ответ 200.
	•	Resend confirmation:
Given подписка pending существует
When клиент вызывает POST /api/v1/subscriptions/{id}/resend-confirmation
Then отправляется новое письмо подтверждения, ответ 202 (или 200 по контракту).
	•	No resend for active:
Given подписка active
When вызывается resend endpoint
Then возвращается 409 (или 400) и письмо не отправляется.

Test Cases (детально):
	•	TC1: Создать подписку → перехватить письмо (mock provider) → проверить наличие ссылок и токена.
	•	TC2: Перейти по confirmation → статус в PG active.
	•	TC3: Resend для pending → письмо отправлено повторно, лимит/троттлинг (если задан) соблюдён.
	•	TC4: Resend для active → ошибка, письмо не отправлено.
	•	TC5: Письмо содержит unsubscribe URL с корректной структурой (пусть даже endpoint в SUB-008).

Dependencies:
	•	SUB-001 (модель и confirm endpoint)
	•	Доступ к email провайдеру / mock; шаблоны (plans/notification_templates.md)

Priority: High
Estimate: 5 SP

⸻

SUB-003 — Push интеграция (FCM/APNs)

Title: SUB-003 — Push channel: device token registration + test push + delivery status webhook

Description:
Реализовать push-канал: регистрацию device_token, отправку тестового push, обработку статусов доставки (callback/webhook или polling — по выбранному провайдеру). Данные хранить в БД, адаптер провайдера — заменяемый.

Acceptance Criteria (Given/When/Then):
	•	Register device token:
Given авторизованный клиент (или иной согласованный механизм идентификации)
When вызывает endpoint регистрации device_token
Then токен сохраняется и возвращается 200/201.
	•	Send test push:
Given для подписки есть активный device_token
When клиент вызывает endpoint test push
Then провайдер вызывается, создаётся запись NotificationRecord, ответ 202.
	•	Delivery status update:
Given провайдер присылает статус delivered/failed
When webhook обработан
Then NotificationRecord обновлён корректно.

Test Cases (детально):
	•	TC1: Register token → проверить запись в PG.
	•	TC2: Test push → проверить вызов адаптера провайдера и NotificationRecord.
	•	TC3: Webhook delivered → статус NotificationRecord=delivered.
	•	TC4: Webhook failed → last_error заполнен, attempts не растут (если это финальный статус).

Dependencies:
	•	SUB-001 (подписки)
	•	SUB-005 (NotificationRecord/поставка уведомлений — если shared model) или отдельная минимальная таблица под push.

Priority: Low (для v1.0 утренней сводки по email — не критично)
Estimate: 8 SP

⸻

SUB-004 — SMS для критических предупреждений

Title: SUB-004 — SMS channel: phone add + verification + send alerts

Description:
Добавить SMS как канал для критических алертов: сбор номера, верификация кодом, отправка сообщений, учёт статусов и попыток. В v1.0 может быть ограничено минимальным API и заглушкой провайдера.

Acceptance Criteria (Given/When/Then):
	•	Add phone + start verification:
Given пользователь вводит номер телефона
When вызывает endpoint добавления номера
Then создаётся verification challenge и отправляется SMS с кодом.
	•	Confirm phone:
Given пользователь вводит корректный код
When вызывает endpoint подтверждения
Then номер помечается verified и доступен для alerts.
	•	Send alert SMS:
Given алерт сработал и канал SMS включён
When диспетчер отправляет SMS
Then создаётся NotificationRecord, статус отражает результат.

Test Cases (детально):
	•	TC1: Add phone → mock provider получил SMS с кодом.
	•	TC2: Confirm корректным кодом → phone verified.
	•	TC3: Trigger alert → NotificationRecord создан, попытки и статусы корректны.
	•	TC4: Provider fail → retry/DLQ (если используется общий pipeline).

Dependencies:
	•	SUB-005 (retry/DLQ)
	•	Провайдер SMS + региональные требования

Priority: Low
Estimate: 13 SP

⸻

SUB-005 — Delivery Pipeline: Dispatcher, Retry и DLQ

Title: SUB-005 — Notification delivery pipeline: queue → dispatcher → provider adapters + retry/DLQ

Description:
Построить delivery pipeline для уведомлений: очередь (EventBus), воркеры-диспетчеры, адаптеры провайдеров. Реализовать retry policy (exponential backoff), DLQ и идемпотентность. Это базис для надёжной доставки email/push/sms.

Acceptance Criteria (Given/When/Then):
	•	Enqueue:
Given создано событие notification.scheduled
When событие публикуется в очередь
Then оно доступно для обработки dispatcher-ом.
	•	Dispatch success path:
Given сообщение в очереди и провайдер доступен
When dispatcher обрабатывает сообщение
Then провайдер вызывается 1 раз, создаётся/обновляется NotificationRecord со статусом dispatched/sent.
	•	Retry on transient failure:
Given провайдер возвращает 5xx/timeout
When dispatcher получает ошибку
Then выполняются ретраи по конфигу, attempts увеличивается, сохраняется last_error.
	•	DLQ on exhausted retries:
Given ретраи исчерпаны
When последняя попытка неуспешна
Then сообщение попадает в DLQ, NotificationRecord помечается failed.
	•	Idempotency:
Given повторное сообщение с тем же idempotency key
When dispatcher обрабатывает повтор
Then дубликат отправки не выполняется, запись не дублируется.

Test Cases (детально):
	•	TC1: enqueue → dispatcher → provider called → NotificationRecord updated.
	•	TC2: provider 5xx → N retries → verify backoff scheduling (минимум факт N попыток).
	•	TC3: after N retries → DLQ contains message, NotificationRecord=failed.
	•	TC4: duplicate idempotency key → only one provider call.

Dependencies:
	•	Решение по EventBus (Kafka/Rabbit/SQS)
	•	SUB-007 (частично, для метрик) — не блокирующая, но желательно параллельно

Priority: Medium (для email утренней сводки можно упрощать, но лучше иметь базис)
Estimate: 13 SP

⸻

SUB-006 — Rules Engine и триггеры (cron/threshold)

Title: SUB-006 — Rules engine: daily cron (morning digest) + threshold triggers → emits notification.scheduled

Description:
Реализовать правила генерации событий уведомлений: cron для ежедневной утренней сводки и threshold-правила (как расширение). Генерировать события в очередь (или напрямую в dispatcher, если pipeline упрощён).

Acceptance Criteria (Given/When/Then):
	•	Create cron rule:
Given подписка active с типом morning
When время соответствует cron-правилу
Then генерируется notification.scheduled для этой подписки.
	•	Bind rule to subscription/location:
Given подписка привязана к city
When правило срабатывает
Then событие содержит нормализованную локацию и ссылку на subscription_id.
	•	Threshold rule (если входит в v1.0 scope):
Given задан threshold (например wind_speed > X)
When входные данные погоды удовлетворяют условию
Then событие генерируется один раз по правилам дедупликации.

Test Cases (детально):
	•	TC1: Cron rule → “время наступило” → событие опубликовано.
	•	TC2: Проверить payload события: subscription_id, city, type, idempotency key.
	•	TC3: Threshold rule → mock weather → событие есть/нет по условию.

Dependencies:
	•	SUB-001 (active subscriptions)
	•	SUB-005 (если доставка через очередь)
	•	Доступ к источнику времени/cron runner (APS/Cloud scheduler)

Priority: Medium (утренняя сводка требует cron)
Estimate: 8 SP

⸻

SUB-007 — Observability: метрики, логи, алерты

Title: SUB-007 — Observability for subscriptions & notifications: metrics + dashboards + alerts + tracing IDs

Description:
Добавить наблюдаемость: метрики API (latency, error rate), метрики доставки (delivery_rate, attempts, DLQ), корреляция request_id/event_id, и алерты. Настроить дашборды в staging/prod.

Acceptance Criteria (Given/When/Then):
	•	Metrics emitted:
Given обработка POST /subscriptions и POST /confirm
When запросы выполняются
Then публикуются метрики latency p50/p95, status codes, error rate.
	•	Delivery metrics:
Given dispatcher отправляет уведомления
When выполняются attempts/retries/DLQ
Then метрики attempts, success/fail, DLQ count обновляются.
	•	Alerts configured:
Given delivery_rate падает ниже порога или DLQ растёт
When выполняются условия
Then алерт срабатывает и содержит ссылку на дашборд/руководство.
	•	Traceability:
Given есть request_id/event_id
When ищем запись в логах/трейсах
Then можно связать API request → событие → попытки доставки.

Test Cases (детально):
	•	TC1: Прогнать тестовый запрос → проверить наличие метрик endpoint-а.
	•	TC2: Симулировать DLQ spike → проверить алерт/правило.
	•	TC3: Проверить корреляцию: request_id присутствует в логах API и dispatcher.

Dependencies:
	•	SUB-005 (для delivery метрик)
	•	Интеграция Prometheus/Grafana/APM

Priority: Medium
Estimate: 5 SP

⸻

SUB-008 — Compliance, Consent и DSR

Title: SUB-008 — Consent + DSR (delete/anonymize) + audit log for subscriptions

Description:
Обеспечить хранение согласия (consent), реализацию DSR (удаление/анонимизация), и аудит-лог всех изменений статуса подписки. Включить ограничения на логирование PII и retention policy (как минимум документ).

Acceptance Criteria (Given/When/Then):
	•	Consent stored on create:
Given пользователь создаёт подписку
When POST /subscriptions успешен
Then consent сохраняется с timestamp и source, доступен для аудита.
	•	DSR request:
Given существует подписка по email
When подан DSR на удаление/анонимизацию
Then контактные данные удалены/анонимизированы, подписка деактивирована, audit log записан.
	•	Audit log:
Given происходит изменение статуса (pending→active, unsubscribe, dsr)
When изменение применяется
Then создаётся audit запись с actor/source и временем.

Test Cases (детально):
	•	TC1: Create subscription → consent record exists with correct fields.
	•	TC2: Confirm → audit log has status change entry.
	•	TC3: DSR → PII удалено/заменено, подписка не активна, audit log есть.
	•	TC4: Повторный DSR → идемпотентное поведение (200/204), без ошибок/дубликатов.

Dependencies:
	•	SUB-001 (данные подписки)
	•	Legal/GDPR согласование по retention и формату

Priority: High (если продукт работает с email — комплаенс обычно блокирующий)
Estimate: 8 SP

⸻

Предлагаемые зависимости и приоритеты (сводка)
	•	High: SUB-001 → SUB-002 → SUB-008 (ядро email-подписки + комплаенс)
	•	Medium: SUB-006 (cron для утренней сводки), SUB-007 (observability), SUB-005 (если требуется надёжная доставка/ретраи)
	•	Low: SUB-003, SUB-004 (каналы push/sms — расширения)

Если нужна “чистая” v1.0 только для утренней email-сводки, практический MVP путь: SUB-001, SUB-002, SUB-006, SUB-008, а SUB-007 как “must-have” перед релизом в прод.
"""

# =================================================================================================
# 4. ДОМАШНЕЕ ЗАДАНИЕ (опционально)
# =================================================================================================

# Улучшение Event Storming v2.0 (опционально)
HOMEWORK_EVENT_STORMING_V2 = """
Actors

1) End User (Web/Mobile)

Роль: управляет подписками и настройками уведомлений, получает уведомления в каналах (in-app/push/email/telegram).
Границы ответственности:
	•	Создание/изменение/удаление подписок и пользовательских правил (пороги, типы алертов, quiet hours, язык, таймзона).
	•	Управление подтверждениями каналов (например, email opt-in / подтверждение Telegram).
	•	Получение истории уведомлений и статусов доставок (read-only).
Критичные моменты продукта:
	•	Идемпотентность UX: повторный клик “подписаться” не должен создавать дубликаты.
	•	Прозрачность: пользователь должен понимать “почему я получил уведомление” (trigger_reason, какие пороги сработали).
	•	Контроль частоты: настройки “не чаще N раз в час/день”, чтобы избежать спама.

⸻

2) External Weather API (Provider)

Роль: источник прогнозов и/или алертов (pull и/или webhook).
Границы ответственности:
	•	Поставляет исходные данные, которые мы не считаем доменной истиной, а рассматриваем как входной сигнал.
	•	Может иметь ограничения по квотам, задержкам, точности, формату полей.
Критичные моменты архитектуры:
	•	Версионирование и дедупликация: один и тот же прогноз может приходить повторно (webhook retries) → нужен provider_event_id / forecast_hash.
	•	Надёжность: частичная недоступность провайдера не должна ломать пользовательский SLA (кэш, last-known-good, деградация).

⸻

3) Scheduler / Orchestrator

Роль: триггерит фоновую обработку: обновление прогнозов, пересчёт правил, “тихие часы” отложенную отправку, ретраи.
Границы ответственности:
	•	Запускает jobs по расписанию и/или шардит города на батчи.
	•	Может быть внешним (cloud scheduler) или внутренним orchestrator’ом.
Критичные моменты:
	•	Backpressure/лимиты: при росте городов и подписок нужен контроль параллелизма и rate-limit к провайдеру.
	•	Ретраи и дедлайны: повторные RefreshForecast не должны множить события.

⸻

4) Delivery Worker / Notification Service

Роль: доставка уведомлений, управление очередью, ретраи, интеграции с FCM/APNs/SMTP/Telegram.
Границы ответственности:
	•	Забирает NotificationScheduled из очереди.
	•	Выполняет доставку по каналам и пишет исходы (Delivered/Failed) с деталями.
Критичные моменты:
	•	Exactly-once недостижим “в чистом виде”: нужны идемпотентные ключи на уровне провайдеров и у нас (dedupe по notification_id+channel).
	•	Политика ретраев: разные стратегии для transient/permanent ошибок.
	•	Метрики продукта: delivery rate, latency, opt-out rate, spam complaints.

⸻

5) Telegram Bot (optional, двунаправленный)

Роль: канал управления подписками и канал доставки.
Границы ответственности:
	•	Принимает команды subscribe/unsubscribe/settings.
	•	Верифицирует связку user_id ↔ telegram_chat_id.
Критичные моменты:
	•	Подтверждение канала: нельзя отправлять в Telegram без явного bind.
	•	Состояния: пользователь может заблокировать бота → это permanent failure для канала.

⸻

Commands (улучшенная версия)

Ниже — команды в терминах домена. У каждой: цель, идемпотентность, валидации и результат. Я добавляю несколько команд, которых не хватает для полноты продукта (управление каналами, настройками, подтверждениями, чтение/статусы).

1) SubscribeToCity

Кто вызывает: Web/Mobile клиент или Telegram Bot
Цель: создать (или активировать) подписку пользователя на город с набором каналов и предпочтений.
Вход:
	•	user_id
	•	city_id
	•	channels[] (telegram/push/email/in-app)
	•	preferences (thresholds, alert_types, quiet_hours, max_frequency, language, timezone)
	•	idempotency_key (рекомендуется для REST)
	•	source (web/mobile/bot)
Валидации/правила:
	•	Пользователь авторизован и имеет доступ к user_id.
	•	city_id существует и поддерживается провайдером.
	•	Нельзя создать дубликат: уникальный ключ (user_id, city_id) + активность; повторный Subscribe → upsert.
	•	Каналы должны быть “подтверждены” (например, email verified, telegram bound, push token exists) — иначе либо ошибка, либо “частичная подписка” (см. ниже).
Результат:
	•	subscription_id
	•	статус: created | reactivated | updated
	•	warnings по неподтверждённым каналам (если выбрана мягкая политика)

⸻

2) UpdateSubscription

Кто вызывает: Web/Mobile или Bot
Цель: изменить каналы/настройки подписки без отписки.
Почему нужно: иначе Subscribe превращается в “швейцарский нож” и сложнее различать intent.
Вход: user_id, subscription_id|city_id, patch(channels, preferences), idempotency_key, source
Валидации:
	•	Подписка принадлежит пользователю.
	•	Изменение quiet hours / frequency должно пересчитать будущие scheduled уведомления (или применять только к новым).
Результат: обновлённая подписка + список изменённых полей.

⸻

3) UnsubscribeFromCity

Кто вызывает: Web/Mobile или Bot
Цель: деактивировать подписку (soft-delete) и отменить будущие уведомления.
Вход:
	•	user_id
	•	city_id или subscription_id
	•	channels(optional) / channels_removed (если поддерживаем частичную отписку по каналу)
	•	source
	•	idempotency_key
Валидации/правила:
	•	Должна существовать активная подписка.
	•	Если channels указан → это “unsubscribe channel(s)” (подписка остаётся активной, если есть другие каналы).
	•	Отмена будущих NotificationScheduled должна быть идемпотентной (например, по subscription_id).
Результат: status: deactivated | channels_updated

⸻

4) BindNotificationChannel (подтверждение канала)

Кто вызывает: клиент (например, после ввода email) или Bot (для Telegram bind)
Цель: привязать/подтвердить канал доставки к пользователю.
Примеры:
	•	Email: отправить код → ConfirmChannel
	•	Push: зарегистрировать device token
	•	Telegram: связать chat_id
Вход: user_id, channel_type, channel_address/token/chat_id, metadata
Результат: channel_state: pending|active

⸻

5) ConfirmNotificationChannel

Кто вызывает: клиент
Цель: активировать канал после подтверждения (email OTP, magic link).
Вход: user_id, channel_type, confirmation_code
Результат: channel_state: active

⸻

6) RefreshForecast

Кто вызывает: scheduler / operator
Цель: получить прогноз для набора городов и зафиксировать “сырой” snapshot; дальше — обработка правил.
Вход:
	•	city_ids[] или batch_cursor
	•	provider_id
	•	force_flag
	•	correlation_id (для трассировки)
Валидации/правила:
	•	Rate limit / квоты провайдера.
	•	Дедуп: если пришёл тот же forecast_hash и forecast_version → не генерировать повторные downstream события.
	•	Хранить raw payload для аудита и отладки (с TTL/ретеншеном).
Результат: fetched_count, skipped_count, failed_count

⸻

7) EvaluateAlerts (явная команда для правил)

Кто вызывает: после WeatherForecastUpdated (внутренний consumer) или scheduler
Цель: сравнить прогноз с предыдущим snapshot и пользовательскими правилами → сформировать алерты.
Почему полезно: отделяет интеграцию провайдера от доменной логики.
Вход: city_id, forecast_version, evaluation_mode(diff|absolute), correlation_id
Результат: список сработавших alert’ов (или 0).

⸻

8) ScheduleNotifications

Кто вызывает: обработчик WeatherAlertTriggered или периодическая рассылка (“ежедневный прогноз в 8:00”)
Цель: создать задачи на доставку уведомлений с учётом quiet hours, frequency caps, доступности каналов.
Вход: alert_id|digest_id, target_users_query|subscription_ids, schedule_policy
Результат: scheduled_count, suppressed_count(quiet_hours/frequency), invalid_channel_count

⸻

9) ProcessNotificationQueue (Delivery)

Кто вызывает: delivery worker
Цель: доставить уведомление по одному/нескольким каналам, записать outcome.
Вход: notification_id, attempt_number, channel(optional)
Правила:
	•	Идемпотентность: повторная обработка не должна создавать дубли в канале (dedupe key).
	•	Retry policy: exponential backoff для transient, stop для permanent.
Результат: NotificationDelivered или NotificationFailed

⸻

Domain Events (улучшенная версия)

Я делаю события более “event-friendly”: добавляю event_id, occurred_at, correlation_id, а также разделяю “технические” детали доставки от доменных причин. Важно: события — это факты, а не команды.

Общие поля (рекомендация для всех событий)
	•	event_id (UUID)
	•	occurred_at (UTC)
	•	correlation_id (для трассировки цепочек)
	•	source (service/component)
	•	schema_version

⸻

1) UserSubscribedToCity

Факт: пользователь создал/активировал подписку на город.
Поля:
	•	user_id
	•	subscription_id
	•	city_id
	•	channels[]
	•	preferences (thresholds, quiet_hours, frequency_caps, alert_types, language, timezone)
	•	created_at (можно оставить как domain timestamp, но лучше использовать occurred_at)
	•	source (web/mobile/bot)
Последствия:
	•	Upsert записи подписки.
	•	Возможный запуск “welcome” уведомления / подсказок.
	•	Пересчёт расписаний (если есть “daily digest”).
Проверки/инварианты:
	•	Уникальность (user_id, city_id) среди активных подписок.
	•	Каналы либо активны, либо подписка создаётся с warnings/ограничениями (это продуктовое решение: строгая или мягкая политика).

⸻

2) SubscriptionUpdated

Факт: изменены каналы или предпочтения подписки.
Поля: user_id, subscription_id, city_id, channels_before/after, preferences_diff, source
Последствия:
	•	Перепланировать будущие уведомления, если затронуты quiet hours/frequency.
	•	Аудит (особенно если изменения через Bot).
Зачем нужно: без этого события сложно объяснять изменения и отлаживать “почему перестало приходить”.

⸻

3) UserUnsubscribedFromCity

Факт: подписка деактивирована или частично отключены каналы.
Поля:
	•	user_id
	•	subscription_id
	•	city_id
	•	channels_removed[] (или unsubscribed_scope: all|channels)
	•	removed_at (или occurred_at)
	•	source
Последствия:
	•	Деактивация/обновление подписки.
	•	Отмена будущих NotificationScheduled по subscription_id.
Проверки:
	•	Событие должно быть идемпотентным: повторная отписка не должна ломать систему.

⸻

4) WeatherForecastFetched (техническое, опционально)

Факт: мы получили ответ от провайдера (успешно/ошибка).
Поля: provider_id, city_id, fetched_at, status(success|failed), http_code, latency_ms, provider_request_id
Зачем: наблюдаемость и SLA к провайдеру.
Примечание: это скорее observability event, не доменный. Можно хранить отдельно от “бизнес-событий”.

⸻

5) WeatherForecastUpdated

Факт: для города зафиксирован новый snapshot прогноза (прошёл дедуп).
Поля (уточнённые):
	•	city_id
	•	provider_id
	•	fetched_at
	•	forecast_version (если есть у провайдера) / forecast_hash
	•	forecast_summary (нормализованное краткое представление)
	•	forecast_payload_raw (сырой JSON, возможно в object storage) + payload_ref
	•	valid_until / ttl_seconds
	•	data_quality (missing_fields_pct, flags)
Последствия:
	•	Сохранить snapshot (Snapshot pattern у вас уже в предпочтениях).
	•	Триггер EvaluateAlerts.
	•	Обновить кэш/Read model.
Проверки:
	•	Валидация схемы, подписи/ключей провайдера (если есть).
	•	Дедуп по forecast_hash + city_id + окну времени.

⸻

6) WeatherAlertTriggered

Факт: сработал алерт определённого типа/серьёзности для города (независимо от конкретного пользователя).
Поля (расширенные):
	•	alert_id
	•	city_id
	•	alert_type (heavy_rain, storm, temp_drop, frost, etc.)
	•	severity (scale + нормализация)
	•	observed_at (время явления по прогнозу/наблюдениям)
	•	trigger_reason (diff vs previous, threshold exceeded, provider alert)
	•	details (структурированно: expected_mm_rain, wind_gust, temp_delta, etc.)
	•	dedupe_key (чтобы не триггерить одинаковый алерт многократно)
Последствия:
	•	ScheduleNotifications по подписчикам города.
	•	Audit запись.
Проверки:
	•	Дедуп: “тот же алерт” в пределах окна (например, 2 часа) не должен плодить уведомления.
	•	Не применять пользовательские quiet hours здесь — это лучше делать на этапе scheduling (иначе будет трудно “догнать” после quiet hours).

⸻

7) NotificationScheduled

Факт: создана задача на доставку уведомления конкретному пользователю (или группе), с плановым временем и каналами.
Поля (уточнённые):
	•	notification_id
	•	user_id
	•	subscription_id (важно для отмены)
	•	city_id
	•	alert_id (или digest_id)
	•	channels[]
	•	scheduled_at
	•	payload_summary
	•	payload_ref (ссылка на полное тело)
	•	status = scheduled
	•	policy_applied (quiet_hours_defer, frequency_cap, channel_availability)
Последствия:
	•	Поставить в broker/queue (по каналам или единым сообщением).
	•	Создать read-model для истории уведомлений.
Проверки:
	•	Каналы должны быть активны на момент scheduling (или помечать как suppressed).
	•	Частота: если превышен cap → либо не создавать, либо создавать со статусом suppressed.

⸻

8) NotificationDeliveryAttempted (опционально, полезно для аналитики)

Факт: воркер попытался доставить по конкретному каналу.
Поля: notification_id, user_id, channel, attempt_number, attempted_at
Зачем: разница между “в очереди” и “реально пытались”.

⸻

9) NotificationDelivered

Факт: доставка по каналу завершилась успехом.
Поля:
	•	notification_id
	•	user_id
	•	channel
	•	delivered_at
	•	provider_msg_id
	•	latency_ms
Последствия:
	•	Обновить статус.
	•	Метрики SLA.
Проверки:
	•	Идемпотентность: повторное “Delivered” для same notification_id+channel не должно ломать агрегаты.

⸻

10) NotificationFailed

Факт: доставка по каналу завершилась ошибкой.
Поля (уточнённые):
	•	notification_id
	•	user_id
	•	channel
	•	failed_at
	•	error_code
	•	error_class (transient|permanent)
	•	retry_count
	•	next_retry_at (если transient)
	•	provider_msg_id (если был)
Последствия:
	•	Если transient → запланировать retry.
	•	Если permanent → отключить канал или пометить “requires user action” (продуктовое решение).
	•	Алёрты на деградацию поставщика.
Проверки:
	•	Корректная классификация ошибок критична, иначе либо спамим ретраями, либо теряем доставку.
"""

# Улучшение Roadmap v2.0 (опционально)
HOMEWORK_ROADMAP_V2 = """
v1.0 — Minimum Lovable Product (MLP)

Цель версии

Проверить “работает ли ценность” погодных уведомлений: пользователи подписываются, подтверждают канал, получают понятные и полезные уведомления и возвращаются/взаимодействуют.

Scope (уточнённый и улучшенный)

Каналы
	•	Email (обязательный для v1.0).
	•	In-app push (если речь про push внутри приложения: это скорее in-app/inbox + локальные пуши; если предполагаются APNs/FCM — это уже внешние push-токены и немного сложнее. Для MLP ок оставить “in-app inbox + простые пуши”).

Подписка и настройки
	•	Подписка на “локацию по умолчанию” (1 город / 1 локация).
	•	Типы уведомлений:
	•	“Daily digest” (утром в фиксированное время по TZ пользователя/локации).
	•	“Severe alerts” (шторм/ливень/мороз/опасная жара — фиксированный набор).
	•	Подтверждение email по ссылке (double opt-in).
	•	Частотные ограничения по умолчанию:
	•	не более X severe-уведомлений в сутки (например, 3), чтобы не “заспамить” при дерганом прогнозе.
	•	Отписка: one-click unsubscribe (обязательно для email).

Контент уведомлений
	•	Digest: кратко (температура мин/макс, осадки/ветер, 1–2 ключевых факта).
	•	Severe: тип опасности + “когда” + “что ожидается” + ссылка/CTA открыть приложение/карточку.

Наблюдаемость и качество
	•	Логи корреляции “подписка → отправка → доставка → клик”.
	•	Дедупликация прогнозов/алертов (минимальная): один алерт одного типа в городе в пределах окна.

API/продуктовые ограничения (осознанно)
	•	Без сложных правил/порогов, без геофенсинга, без истории.
	•	Без SMS/Telegram.
	•	Минимальная админка (можно вообще без UI, только профиль/страница).

Метрики успеха (North Star + supporting)

Activation / Value
	•	Email confirmation rate: % подтвердивших email от начавших подписку.
	•	Subscription activation time: медиана времени “создал → подтвердил”.
	•	Notification CTR (для email и пушей отдельно): клики / доставленные.

Delivery / Reliability
	•	Email deliverability: delivered / sent (а также bounce rate).
	•	Push delivery rate (если есть внешний пуш): delivered / attempted.
	•	Median send latency: время от “alert triggered/scheduled” до “delivered”.

Retention (ранний сигнал)
	•	7-day retention среди подписавшихся (или DAU/WAU uplift у подписчиков vs контроль).
	•	Unsubscribe rate: отписки / активные подписки (по неделе).

Целевые ориентиры (примерно, для принятия решений)
	•	Confirmation rate: 50–70%+ (если ниже — проблема с UX/доверия/попаданием в спам).
	•	Bounce rate: <2–5%.
	•	Severe CTR: зависит от канала, но важно сравнение с digest (severe обычно выше).

⸻

v1.1 — Надёжность доставки и управление подпиской

Цель версии

Сделать систему “доверяемой”: пользователь видит статус, может управлять каналами, доставка становится предсказуемой; добавить SMS как “канал последней надежды” для критических случаев.

Scope (уточнённый и улучшенный)

Управление подпиской
	•	Панель в профиле:
	•	включить/выключить уведомления,
	•	выбрать каналы (email/push, SMS — отдельно как “critical only”),
	•	выбрать типы (digest vs severe),
	•	показать текущую локацию/город.
	•	“Тестовое уведомление” для каждого канала:
	•	отправить тест на email,
	•	пуш (если поддерживается),
	•	SMS (если включен).

Статус и диагностика
	•	Статус подписки: active/pending_email/failed_delivery/channel_unverified.
	•	Причины деградации: “email bounced”, “push token invalid”, “sms provider error”.

SMS (как опция)
	•	Только для Critical alerts (например, severity >= high).
	•	Верификация телефона (OTP).
	•	Ограничение частоты и стоимость:
	•	дневной лимит SMS на пользователя,
	•	глобальный бюджет/лимит на систему.

Retry policy и очереди
	•	Явная политика ретраев:
	•	transient → ретраи с backoff,
	•	permanent → stop + пометка канала.
	•	Мониторинг задержек очереди (queue lag), ошибки провайдеров.

Качество контента
	•	Unified шаблоны: одинаковый смысл в email/push/sms (разный формат).

Метрики успеха

Trust / Control
	•	Test notification success rate: % успешных тестовых уведомлений по каналам.
	•	Self-serve change rate: доля пользователей, которые меняют настройки без обращения в поддержку (если есть support).

Delivery
	•	Delivery success rate by channel (email/push/sms).
	•	Time-to-deliver P95 для severe/critical.
	•	Retry effectiveness: доля сообщений, доставленных после 1+ ретрая.
	•	Provider error rate (по каждому провайдеру).

Cost / Efficiency
	•	SMS cost per active critical subscriber.
	•	Critical SMS volume: SMS/день и доля “полезных” (proxy: CTR/открытия, если возможно, или снижение отписок).

User outcomes
	•	Unsubscribe rate должен снижаться относительно v1.0 (или хотя бы не расти при росте объёма).
	•	Complaint signals: spam complaints, block bot, bounce growth.

Ориентиры
	•	P95 latency severe: целевое окно (например, <60–120 секунд после trigger, зависит от архитектуры).
	•	SMS fail rate: минимизировать, но важнее “конверсия критических доставок” (fallback).

⸻

v2.0 — Персонализация и расширенные сценарии

Цель версии

Сделать уведомления “не просто полезными, а незаменимыми”: высокая релевантность, сценарии по месту и поведению, богатый формат, платформа под монетизацию/премиум.

Scope (уточнённый и улучшенный)

Гибкие правила (персонализация)
	•	Custom thresholds:
	•	ветер > X,
	•	осадки > Y мм,
	•	температура < / > Z,
	•	резкое изменение (дельта за N часов).
	•	Комбинаторика правил ограничена (чтобы не взорвать UX):
	•	presets + advanced mode.
	•	Quiet hours + “catch-up delivery” (после quiet hours отправить, если алерт ещё актуален).

Локации и геофенсинг
	•	Несколько локаций/городов на пользователя.
	•	Геофенсинг:
	•	home/work/“where I am now”.
	•	Приоритет локаций: текущая > избранные > домашняя.

Rich notifications
	•	Карточка риска:
	•	период действия,
	•	confidence (если есть),
	•	рекомендации (что делать),
	•	CTA (подробнее, поделиться, настроить пороги).
	•	Картинка/иконки, deep-link в приложение.

История и аналитика
	•	Inbox/история уведомлений:
	•	статус доставки,
	•	“почему сработало” (trigger_reason),
	•	feedback (полезно/неполезно, слишком часто).
	•	Аналитика реакций:
	•	open rate, CTR,
	•	suppressions (quiet hours/frequency caps),
	•	негативные сигналы.

SLA/SLI
	•	Формализация SLO:
	•	delivery success,
	•	latency,
	•	data freshness (как давно обновляли прогноз).
	•	Алертинг для on-call.

Монетизация (опциональный трек, но подготовка)
	•	Premium:
	•	больше локаций,
	•	advanced rules,
	•	“early warnings”,
	•	richer insights.
	•	Важно: не смешивать в одной версии “core value” и “пейволл без ценности”.

Метрики успеха

Product value / Retention
	•	Subscriber 30-day retention (ключевая на этом этапе).
	•	DAU/WAU среди подписчиков и uplift vs не-подписчики.
	•	Notification relevance score:
	•	% “полезно” в feedback,
	•	“mute / отключил тип” как негативный сигнал.

Personalization adoption
	•	Share of users using custom thresholds.
	•	Avg number of rules per user (контролируемый рост).
	•	Geofence adoption rate и доля уведомлений по geofence vs статическим локациям.

Quality & Spam control
	•	Notifications per user per day (median, P95).
	•	Suppression rate (quiet hours/frequency caps) — как показатель, что система умеет себя ограничивать.
	•	Mute/disable rate по типам алертов.

SLA/Operations
	•	P95 end-to-end latency по critical/severe/digest отдельно.
	•	Forecast freshness: P95 “возраст” прогноза на момент вычисления алерта.
	•	Dedup rate: доля предотвращённых дублей (важно для стабильности UX).

Монетизация (если включаем)
	•	Conversion to premium (trial → paid).
	•	ARPPU / churn premium.
	•	Attach rate: доля подписчиков, включивших premium-фичи.
"""

# Chain of Thought (многоэтапный промптинг)
HOMEWORK_MULTIPROMPT_TASK = """
Сформировать спецификацию REST API контракта для WeatherService v1.0
"""

HOMEWORK_MULTIPROMPT_STEPS = """
1) Определить доменную модель и REST ресурсы, состояния и переходы между ними.
2) Спроектировать эндпоинты 
3) Зафиксировать контракт ошибок и идемпотентности
4) Собрать финальную спецификацию в Markdown
"""

HOMEWORK_MULTIPROMPT_SEQUENCE = """
Шаг 1:
[R] Действуй как Backend-разработчик/API Architect с опытом проектирования публичных REST API
[C] WeatherService v1.0: POST /subscribe (email+city), email confirm link, PG subscriptions, Redis cache TTL 600s, OWM validation
[T] Определи доменную модель для подписки и подтверждения: сущности, поля, статусы, инварианты, state machine
[F] Ответ оформи в md: таблица сущностей + state diagram текстом + список инвариантов

- составлена таблица доменных сущностей
- есть текстовое описание State diagram
- описаны инварианты

Шаг 2:
[R] Действуй как Senior API Designer с большим коммерческим опытом
[C] Используй результат шага 1 как источник истины. Нужен минимальный публичный REST API для v1.0
[T] Спроектируй эндпоинты: create subscription, confirm, get subscription, unsubscribe. Определи request/response и статус-коды.
[F] Таблица эндпоинтов + краткие JSON схемы (поля и типы) и примеры response

- получена таблица эндпоинтов
- дано описание JSON схем
- прописаны общие соглашения

Шаг 3:
[R] Действуй как Senior QA 
[C] Используй эндпоинты из шага 2.
[T] Определи единый error schema, перечень ошибок по каждому endpoint, идемпотентность
[F] Markdown: error schema и матрица ошибок (endpoint → code → причина) и правила идемпотентности

- описана единая error schema
- получена матрица ошибок
- описаны правила идемпотентности

Шаг 4:
[R] Действуй как опытный Tech Writer для API документации
[C] Собери спецификацию v1.0 из шагов 1–3 и сверяйся с Acceptance Criteria.
[T] Собери финальный документ “WeatherService API Contract v1.0” с примерами запросов и ответов.
[F] Один md документ с разделами Overview, Resources, Endpoints, Errors, Idempotency, Examples

- получен единый финальный документ
"""

HOMEWORK_MULTIPROMPT_RESULT = """
# WeatherService API Contract v1.0

## Overview

WeatherService v1.0 предоставляет минимальный публичный REST API для подписки на погодные уведомления по выбранному городу. Основной сценарий: пользователь отправляет запрос на подписку (`POST /subscriptions`), получает письмо с ссылкой подтверждения и активирует подписку через `POST /subscriptions/confirm`.

**Сценарии v1.0**
- Создать подписку на **утреннюю email-сводку** по городу (status=`pending`)
- Подтвердить email по ссылке (status=`active`)
- Получить текущее состояние подписки
- Отписаться (soft-delete, status=`unsubscribed`)
- Валидация города через OpenWeatherMap (OWM)
- Кэш данных погоды в Redis с TTL 600 секунд

**Набор каналов**
- `email` — основной канал v1.0  
*(in-app/push могут присутствовать как расширение, но в рамках контракта v1.0 считаются опциональными)*

**Time format**
- Все timestamps: ISO 8601 в UTC, например: `2026-02-25T10:15:30Z`

**Base URL**
- `https://<host>/api/v1`

---

## Resources

### Subscription

Подписка пользователя на уведомления для города.

**Идентификаторы**
- `id` (UUID) — primary key
- Уникальность: `(email_normalized, city_normalized, notification_type)` среди подписок со статусом `pending` или `active`

**Поля**
- `email_masked` (string) — email в маскированном виде в публичных ответах
- `email_normalized` (string, internal) — нормализованный email
- `city` (string) — исходный ввод (может не возвращаться публично)
- `city_normalized` (string) — нормализованное значение города
- `notification_type` (enum) — `morning_digest` (v1.0)
- `channels` (array enum) — `["email"]` (v1.0)
- `timezone` (string, IANA TZ) — например `Europe/Helsinki`
- `status` (enum) — `pending | active | unsubscribed`
- `created_at` (timestamp)
- `confirmed_at` (timestamp, nullable)
- `unsubscribed_at` (timestamp, nullable)
- `consent_at` (timestamp, internal/optional to expose)
- `source` (enum string) — `web | mobile | api` (для аудита)

### EmailConfirmationToken

Одноразовый токен подтверждения email, выпущенный для конкретной подписки.

**Поля (internal)**
- `subscription_id` (UUID)
- `token_hash` (string)
- `expires_at` (timestamp)
- `used_at` (timestamp, nullable)
- `resent_count` (int)
- `last_sent_at` (timestamp, nullable)

---

### State machine (Subscription)

- `pending` → `active` (по успешному confirm токеном)
- `pending` → `unsubscribed` (unsubscribe допускается, если политика разрешает)
- `active` → `unsubscribed` (unsubscribe)
- `unsubscribed` — terminal в v1.0

---

### Инварианты (обязательные правила)

1. **Уникальность подписки:** нельзя создать 2 подписки со статусом `pending/active` с одинаковой тройкой `(email_normalized, city_normalized, notification_type)`.
2. **Валидация города:** создание подписки требует успешной проверки города через OWM; если город не распознан — подписка не создаётся.
3. **Токен подтверждения одноразовый:** повторное использование запрещено; токен имеет TTL.
4. **Подтверждение обязательно:** `active` возможен только после `confirm`.
5. **PII safety:** в публичных ответах возвращается `email_masked`, raw token не возвращается.
6. **Redis кэш погоды:** TTL = 600 секунд (cache-aside); источник данных помечается как `cache|provider`.

---

## Endpoints

### 1) Create Subscription

**POST** `/subscriptions`

Создаёт подписку со статусом `pending`, валидирует город через OWM, инициирует отправку письма подтверждения.

#### Request

```json
{
  "email": "string",
  "city": "string",
  "notification_type": "morning_digest",
  "channels": ["email"],
  "timezone": "Europe/Helsinki",
  "source": "web"
}

Полевая схема
	•	email (string, required)
	•	city (string, required)
	•	notification_type (enum, optional, default=morning_digest)
	•	channels (array enum, optional, default=["email"])
	•	timezone (string, optional)
	•	source (string, optional)

Response — 201 Created

{
  "subscription": {
    "id": "uuid",
    "email_masked": "u***@example.com",
    "city_normalized": "Helsinki",
    "notification_type": "morning_digest",
    "channels": ["email"],
    "status": "pending",
    "timezone": "Europe/Helsinki",
    "created_at": "2026-02-25T10:15:30Z"
  },
  "confirmation": {
    "method": "email_link",
    "expires_at": "2026-02-25T11:15:30Z"
  },
  "weather": {
    "source": "cache|provider",
    "cached_ttl_seconds": 600,
    "summary": {
      "temp_c": 2.3,
      "wind_mps": 4.2,
      "precip_mm": 0.0
    }
  }
}

Status codes
	•	201 — подписка создана (pending)
	•	400 — невалидный запрос или город не распознан
	•	409 — дубликат подписки
	•	429 — превышен лимит запросов
	•	503 — OWM недоступен при обязательной валидации

⸻

2) Confirm Subscription

POST /subscriptions/confirm

Подтверждает email по токену из письма и переводит подписку pending → active.

Request

{
  "token": "string"
}

Response — 200 OK

{
  "subscription": {
    "id": "uuid",
    "status": "active",
    "confirmed_at": "2026-02-25T10:20:00Z"
  }
}

Status codes
	•	200 — подтверждено, подписка активна
	•	400 — токен невалиден/истёк
	•	404 — токен/подписка не найдены
	•	409 — токен уже использован (может быть 200 при идемпотентном confirm)
	•	429 — rate limit / анти-брутфорс

⸻

3) Get Subscription

GET /subscriptions/{subscription_id}

Возвращает текущее состояние подписки.

Response — 200 OK

{
  "subscription": {
    "id": "uuid",
    "email_masked": "u***@example.com",
    "city_normalized": "Helsinki",
    "notification_type": "morning_digest",
    "channels": ["email"],
    "status": "active",
    "timezone": "Europe/Helsinki",
    "created_at": "2026-02-25T10:15:30Z",
    "confirmed_at": "2026-02-25T10:20:00Z",
    "unsubscribed_at": null
  }
}

Status codes
	•	200 — найдено
	•	404 — не найдено
	•	401/403 — нет доступа (если используется auth)

⸻

4) Unsubscribe

POST /subscriptions/{subscription_id}/unsubscribe

Переводит подписку в статус unsubscribed (soft-delete). Рекомендуется идемпотентное поведение: повторный вызов возвращает 200 и текущий статус.

Request (optional)

{
  "reason": "user_request",
  "source": "web"
}

Response — 200 OK

{
  "subscription": {
    "id": "uuid",
    "status": "unsubscribed",
    "unsubscribed_at": "2026-02-25T12:00:00Z"
  }
}

Status codes
	•	200 — отписка выполнена (или уже была выполнена)
	•	404 — подписка не найдена
	•	401/403 — нет доступа

⸻

Errors

Error schema

{
  "error": {
    "code": "string",
    "message": "string",
    "details": {
      "field": "string",
      "reason": "string",
      "meta": {}
    },
    "correlation_id": "string",
    "retryable": true
  }
}

Error codes

error.code	HTTP	Описание
validation_failed	400	Ошибка валидации входных данных
unknown_city	400	Город не распознан OWM
duplicate_subscription	409	Дубликат подписки
token_invalid	400	Токен некорректен
token_expired	400	Токен истёк
token_used	409 (или 200)	Токен уже использован
subscription_not_found	404	Подписка не найдена
not_authorized	401	Нет авторизации
forbidden	403	Нет прав
rate_limited	429	Rate limit
provider_unavailable	503	OWM недоступен
internal_error	500	Внутренняя ошибка


⸻

Idempotency

POST /subscriptions (Create)

Рекомендуется поддержать Idempotency-Key header для безопасного повторения при сетевых сбоях.
	•	Header: Idempotency-Key: <uuid>
	•	Повтор запроса с тем же ключом и тем же payload → возвращает тот же результат (HTTP+body).
	•	Повтор с тем же ключом и другим payload → 409 (рекомендуется отдельный idempotency_key_conflict, либо validation_failed).

Минимально допустимо (если ключ не реализован): “естественная идемпотентность” через уникальный индекс, но тогда повтор вернёт 409 duplicate_subscription.

POST /subscriptions/confirm (Confirm)

Рекомендуется идемпотентный confirm:
	•	если токен уже использован / подписка уже active → 200 OK с текущим статусом.

POST /subscriptions/{id}/unsubscribe

Рекомендуется идемпотентный unsubscribe:
	•	повторная отписка → 200 OK и status=unsubscribed.

⸻

Examples

Example A — Create subscription (happy path)

Request

POST /api/v1/subscriptions
Content-Type: application/json
Idempotency-Key: 3f6b0dd0-6d6b-4d5a-8b4f-0c90f48a9f1a

{
  "email": "user1@example.com",
  "city": "Helsinki",
  "notification_type": "morning_digest",
  "channels": ["email"],
  "timezone": "Europe/Helsinki",
  "source": "web"
}

Response (201)

{
  "subscription": {
    "id": "8d3d3f4c-79af-4c8e-bc64-8a62b2a9f7c1",
    "email_masked": "u***@example.com",
    "city_normalized": "Helsinki",
    "notification_type": "morning_digest",
    "channels": ["email"],
    "status": "pending",
    "timezone": "Europe/Helsinki",
    "created_at": "2026-02-25T10:15:30Z"
  },
  "confirmation": {
    "method": "email_link",
    "expires_at": "2026-02-25T11:15:30Z"
  },
  "weather": {
    "source": "provider",
    "cached_ttl_seconds": 600,
    "summary": {
      "temp_c": 2.3,
      "wind_mps": 4.2,
      "precip_mm": 0.0
    }
  }
}


⸻

Example B — Confirm subscription

Request

POST /api/v1/subscriptions/confirm
Content-Type: application/json

{
  "token": "raw-token-from-email-link"
}

Response (200)

{
  "subscription": {
    "id": "8d3d3f4c-79af-4c8e-bc64-8a62b2a9f7c1",
    "status": "active",
    "confirmed_at": "2026-02-25T10:20:00Z"
  }
}


⸻

Example C — Duplicate subscription

Response (409)

{
  "error": {
    "code": "duplicate_subscription",
    "message": "Subscription already exists for the given email, city and notification type.",
    "details": {
      "field": "email,city,notification_type",
      "reason": "duplicate",
      "meta": {}
    },
    "correlation_id": "c-9b2c1f9c2e5f4d9a",
    "retryable": false
  }
}


⸻

Example D — Unknown city

Response (400)

{
  "error": {
    "code": "unknown_city",
    "message": "City is not recognized by the weather provider.",
    "details": {
      "field": "city",
      "reason": "not_found",
      "meta": {
        "provider": "OWM"
      }
    },
    "correlation_id": "c-07acb94fbf1f4a2d",
    "retryable": false
  }
}


⸻

Example E — Unsubscribe (idempotent)

Request

POST /api/v1/subscriptions/8d3d3f4c-79af-4c8e-bc64-8a62b2a9f7c1/unsubscribe
Content-Type: application/json

{
  "reason": "user_request",
  "source": "web"
}

Response (200)

{
  "subscription": {
    "id": "8d3d3f4c-79af-4c8e-bc64-8a62b2a9f7c1",
    "status": "unsubscribed",
    "unsubscribed_at": "2026-02-25T12:00:00Z"
  }
}

"""

# =================================================================================================
# 5. РЕФЛЕКСИЯ
# =================================================================================================
REFLECTION = {
    "before_after": """
    С явным указанием роли получается более стабильный уровень продуманности на каждом шаге. 
    Также прописывание контекста явно позволяет быть уверенным в том, что модель будет давать ответ на основе имеющихся данных с меньшими галлюцинациями.
    Указание формата хорошо помогает сразу получить то, что тебе нужно, без необходимости дорабатывать для соответствия оформлению
    """,
    
    "hardest_part": "Для меня сложнее всего описывать формат, когда он явно не ограничен общепринятыми правилами.",
}

# =================================================================================================
# ЭКСПОРТ
# =================================================================================================
def export_report():
    if "TODO" in STUDENT_INFO["full_name"]:
        print("❌ ОШИБКА: Заполните информацию о студенте.")
        return

    report = f"# Отчет по Практике 2: {STUDENT_INFO['full_name']}\n\n"
    report += "## 1. Анализ промптов R.C.T.F.\n\n"
    
    if not PROMPT_LOGS:
        report += "⚠️ Журнал пуст!\n"
    
    for log in PROMPT_LOGS:
        report += f"### {log.task_name}\n"
        report += f"**Role:** {log.role}\n"
        report += f"**Context:** {log.context}\n"
        report += f"**Task:** {log.task}\n"
        report += f"**Format:** {log.format}\n"
        report += f"**Результат:** {log.result}\n"
        report += "---\n"

    report += "## 2. Улучшенные артефакты\n\n"
    report += "### Mermaid v2\n```mermaid\n" + MERMAID_V2 + "\n```\n\n"
    report += "### Gherkin Scenarios\n```gherkin\n" + GHERKIN_SCENARIOS + "\n```\n\n"
    report += "### DoR v2.0\n" + DOR_V2 + "\n\n"
    report += "### DoD v2.0\n" + DOD_V2 + "\n\n"
    report += "### Test Plan v2\n" + TEST_PLAN_V2 + "\n\n"
    report += "### Functional Delivery v2.0\n" + FUNCTIONAL_DELIVERY_V2 + "\n\n"

    report += "## 3. Домашнее задание\n\n"
    if HOMEWORK_EVENT_STORMING_V2 and "TODO" not in HOMEWORK_EVENT_STORMING_V2:
        report += "### Event Storming v2.0\n" + HOMEWORK_EVENT_STORMING_V2 + "\n\n"
    if HOMEWORK_ROADMAP_V2 and "TODO" not in HOMEWORK_ROADMAP_V2:
        report += "### Roadmap v2.0\n" + HOMEWORK_ROADMAP_V2 + "\n\n"
    if HOMEWORK_MULTIPROMPT_TASK and "TODO" not in HOMEWORK_MULTIPROMPT_TASK:
        report += "### Chain of Thought\n"
        report += "**Задача:** " + HOMEWORK_MULTIPROMPT_TASK + "\n\n"
        report += "**Шаги:** " + HOMEWORK_MULTIPROMPT_STEPS + "\n\n"
        report += "**Последовательность:** " + HOMEWORK_MULTIPROMPT_SEQUENCE + "\n\n"
        report += "**Результат:** " + HOMEWORK_MULTIPROMPT_RESULT + "\n\n"
    
    report += "## 4. Рефлексия\n\n"
    report += f"**Before/After:** {REFLECTION['before_after']}\n\n"
    report += f"**Сложности:** {REFLECTION['hardest_part']}\n"

    os.makedirs("artifacts", exist_ok=True)
    with open("artifacts/report_p2.md", "w", encoding="utf-8") as f:
        f.write(report)
    print(f"✅ Отчет успешно сгенерирован: artifacts/report_p2.md")

if __name__ == "__main__":
    export_report()
