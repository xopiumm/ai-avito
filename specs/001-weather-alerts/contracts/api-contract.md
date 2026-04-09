# API контракт: Weather Alerts

## Публичный REST API

### Создание подписки

`POST /api/v1/subscriptions`

**Запрос**

```json
{
  "location": { "id": "location-id-or-normalized-key" },
  "conditions": [
    { "type": "rain_probability_above", "threshold": 70 },
    { "type": "temperature_below", "threshold": -10 }
  ],
  "conditionMode": "ANY",
  "schedule": {
    "timezone": "location",
    "activeFrom": "08:00",
    "activeTo": "20:00"
  },
  "deliveryChannels": [
    { "type": "email", "address": "user@example.com", "active": true },
    { "type": "push", "token": "push-token", "active": true },
    { "type": "webhook", "url": "https://example.com/webhook", "active": true }
  ]
}
```

**Ответ**

- `201 Created` при успешном создании.
- `400 Bad Request` при некорректном расписании или неоднозначной локации.
- `422 Unprocessable Entity` при неподдерживаемом типе условия или канала.

### Список подписок

`GET /api/v1/subscriptions`

Возвращает подписки авторизованного пользователя.

### Получение подписки

`GET /api/v1/subscriptions/{subscriptionId}`

Возвращает одну подписку вместе с условиями, каналами и расписанием.

### Обновление подписки

`PATCH /api/v1/subscriptions/{subscriptionId}`

Поддерживает частичное обновление условий, каналов и расписания.

### Временное отключение подписки

`POST /api/v1/subscriptions/{subscriptionId}/disable`

Временно приостанавливает оценку условий и отправку уведомлений.

### Повторное включение подписки

`POST /api/v1/subscriptions/{subscriptionId}/enable`

Возвращает отключенную подписку в активное состояние.

### Удаление подписки

`DELETE /api/v1/subscriptions/{subscriptionId}`

Удаляет подписку и отменяет связанные pending/retry попытки.

## Внутренние контракты событий

### Погодное событие

```json
{
  "eventId": "evt_123",
  "locationId": "loc_123",
  "eventType": "rain_probability_above",
  "forecastDate": "2026-04-10",
  "sourceTimestamp": "2026-04-09T10:00:00Z",
  "payload": {
    "rainProbability": 75,
    "temperature": -12,
    "windSpeed": 8
  }
}
```

### Результат доставки

```json
{
  "subscriptionId": "sub_123",
  "channel": "email",
  "weatherEventType": "rain_probability_above",
  "status": "sent",
  "attempt": 1,
  "dedupKey": "dedup:user123:sub123:email:rain_probability_above",
  "timestamp": "2026-04-09T10:01:00Z"
}
```

## Правила контракта

- Несколько условий внутри одной подписки оцениваются по логике ANY.
- Область дедупликации: user + subscription + channel + event type с TTL 12 часов.
- При закрытом окне доставки формируется pending-уведомление.
- Ошибка одного канала не должна блокировать остальные каналы.
- Повторная обработка одного и того же события должна быть идемпотентной.