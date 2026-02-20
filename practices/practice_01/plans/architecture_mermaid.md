# Architecture diagram (Mermaid) — Подписки и Уведомления (WeatherService)

Ниже диаграмма компонентов и связей, основанная на принятом архитектурном решении (async pipeline, queue, dispatcher, provider adapters).

```mermaid
flowchart LR
  subgraph Client[Клиент]
    UI[Web/Mobile App]
  end

  UI -->|REST / GraphQL| API[API Gateway]
  API --> Auth[Auth Service]
  API --> SubSvc[Subscription Service\n(Postgres)]
  API --> AdminUI[Admin / UX]

  Rules[Rules Engine / Scheduler] -->|plan/trigger| EventBus((Message Queue\nKafka / Rabbit / SQS))
  SubSvc -->|enqueue| EventBus

  EventBus --> Dispatcher[Dispatcher / Worker Pool]
  Dispatcher --> AdapterEmail[Email Adapter (SendGrid/SES)]
  Dispatcher --> AdapterSMS[SMS Adapter (Twilio / Local)]
  Dispatcher --> AdapterPush[Push Adapter (FCM / APNs)]

  AdapterEmail --> ProviderEmail[Email Provider]
  AdapterSMS --> ProviderSMS[SMS Provider]
  AdapterPush --> ProviderPush[Push Provider]

  ProviderEmail -->|webhook status| Webhook[/hooks/provider/delivery]
  ProviderSMS --> Webhook
  ProviderPush --> Webhook
  Webhook --> API

  Dispatcher --> DLQ[(Dead Letter Queue)]

  Dispatcher --> Observ[Observability / Tracing / Metrics]
  EventBus --> Observ
  SubSvc --> ConsentStore[Consent & Audit Log]
  ConsentStore --> Compliance[Compliance / DSR]

  classDef infra stroke:#333,stroke-width:1px,fill:#f9f9f9;
  class EventBus,Dispatcher,DLQ infra;
```

Легенда:
- API Gateway — входная точка для UI и внутренних вызовов.
- Subscription Service — хранение подписок, согласий и управление статусами.
- Rules Engine / Scheduler — генерирует события по правилам (cron/thresholds).
- Event Bus — очередь сообщений между компонентами.
- Dispatcher — рабочие процессы, которые формируют final payload и отправляют провайдерам.
- Provider Adapters — абстракция над внешними почтовыми/SMS/push сервисами.
- DLQ — хранилище сообщений после исчерпания retry-политики.
- Observability — метрики, дашборды и трассировка (tracing headers).

Файл сохранён как [`plans/architecture_mermaid.md`](plans/architecture_mermaid.md:1).