# Notification Templates and Payloads (WeatherService)

Файл содержит набор шаблонов уведомлений и примеров payload, пригодных для frontend и notification-service.

## 1. Общие принципы шаблонов
- Шаблоны должны быть локализуемыми (i18n keys).
- Содержать минимально необходимую информацию: заголовок, основной текст, локация, время действия, уровень риска, CTA.
- Rich notifications (v2.0) поддерживают image_url и action_url.

## 2. Шаблоны

1) Утренний прогноз (daily_summary)
- Title (i18n): weather.daily_summary.title
- Body (i18n): weather.daily_summary.body
- Params: { location, high_temp, low_temp, condition }

Payload (internal event):
{
  "notification_id": "notif-uuid",
  "channel": "email",
  "template": "daily_summary",
  "locale": "ru",
  "data": {
    "location": "Moscow",
    "high_temp": "+7°C",
    "low_temp": "+1°C",
    "condition": "rain"
  },
  "meta": { "valid_until": "2026-02-13T09:00:00Z" }
}

2) Критическое предупреждение (alert)
- Title: weather.alert.title
- Body: weather.alert.body
- Params: { location, risk_level, recommended_actions, starts_at, ends_at }

Payload:
{
  "notification_id": "notif-uuid",
  "channel": "sms",
  "template": "alert",
  "locale": "ru",
  "data": {
    "location": "Saint Petersburg",
    "risk_level": "high",
    "recommended_actions": "stay indoors",
    "starts_at": "2026-02-13T04:00:00Z",
    "ends_at": "2026-02-13T10:00:00Z"
  }
}

3) Тестовое уведомление (test)
- Title: weather.test.title
- Body: weather.test.body
- Params: { note }

Payload:
{
  "notification_id": "notif-uuid",
  "channel": "push",
  "template": "test",
  "data": { "note": "This is a test" }
}

4) Подтверждение подписки (confirmation)
- Title: weather.confirmation.title
- Body: weather.confirmation.body
- Params: { confirmation_link }

Payload:
{
  "notification_id": "notif-uuid",
  "channel": "email",
  "template": "confirmation",
  "data": { "confirmation_link": "https://weather.example/confirm?token=abc" }
}

5) Отписка и политика (unsubscribe)
- Title: weather.unsubscribe.title
- Body: weather.unsubscribe.body
- Params: { unsubscribe_link }

Payload:
{
  "notification_id": "notif-uuid",
  "channel": "email",
  "template": "unsubscribe",
  "data": { "unsubscribe_link": "https://weather.example/unsubscribe?token=xyz" }
}

## 3. Примеры payload для frontend (push и web)
- Push payload (FCM/APNs generic):
{
  "to": "device_token",
  "notification": { "title": "Утренний прогноз", "body": "Дождь, +5°C", "click_action": "OPEN_APP" },
  "data": { "notification_id": "notif-uuid", "meta": { "location": "Moscow" } }
}

- Web push (VAPID):
{
  "title": "Предупреждение: сильный ветер",
  "body": "Шквал ветра до 20 м/с в вашем районе.",
  "data": { "url": "https://weather.example/alerts/123" }
}

## 4. Substitution и i18n
- Шаблоны должны использовать placeholders, например: "weather.alert.body": "Внимание в [location]: [risk_level] — [recommended_actions]"
- Перед рендерингом необходимо валидировать наличие всех обязательных params и fallback-значений.

## 5. Acceptance criteria
- Все шаблоны имеют примеры payload и ключи i18n.
- Notification-service может собирать данные, рендерить шаблон под locale и отправлять соответствующему provider.
- Frontend может обработать push payload и показать корректный deeplink/CTA.

---

Файл создан в `plans/notification_templates.md`. Откройте для проверки: [`plans/notification_templates.md`](plans/notification_templates.md:1).