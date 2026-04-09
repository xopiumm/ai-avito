# T015: Schedule Service (Weather Alerts)

**Статус**: ✅ Завершено  
**Дата**: 9 апреля 2026  
**Автор**: AI Engineering Assistant  

## Описание

Реализован сервис проверки расписания доставки (`ScheduleService`) для Weather Alerts. Сервис обеспечивает timezone-осознанные проверки окна доставки и расчеты времени для pending-уведомлений.

## Реализованные компоненты

### 1. Основной сервис: `ScheduleService`

**Файл**: `src/weather_alerts/services/schedule_service.py`

**Интерфейс**:
```python
class ScheduleService:
    def check_schedule(
        self,
        subscription: Subscription,
        check_time_utc: datetime,
    ) -> ScheduleCheckResult:
        """Check if delivery is allowed at a specific time."""
    
    def get_next_delivery_window(
        self,
        subscription: Subscription,
        current_time_utc: datetime,
    ) -> Optional[NextDeliveryWindow]:
        """Get information about next allowed delivery window."""
```

**Возможности**:
- ✅ Timezone-осознанная проверка расписания (используется часовой пояс локации)
- ✅ Поддержка активного окна в формате HH:MM (e.g., "08:00"-"20:00")
- ✅ Поддержка отсутствия окна (NULL active_from/active_to = доставка всегда разрешена)
- ✅ Проверка граничных условий (ровно в начале/конце окна)
- ✅ Расчет ближайшего допустимого времени для pending-уведомлений
- ✅ Конвертация UTC ↔ Local timezone

### 2. Статус расписания: `ScheduleStatus`

```python
class ScheduleStatus(str, Enum):
    ALLOWED = "allowed"                      # Доставка разрешена
    PENDING_WINDOW_CLOSED = "pending_window_closed"  # Окно закрыто, ждем открытия
    NO_WINDOW = "no_window"                  # Нет ограничений по времени
```

### 3. Результат проверки: `ScheduleCheckResult`

```python
@dataclass
class ScheduleCheckResult:
    subscription_id: int          # ID подписки
    status: ScheduleStatus        # Статус (ALLOWED, PENDING_WINDOW_CLOSED, NO_WINDOW)
    is_allowed: bool              # Удобный boolean флаг
    current_time_local: datetime  # Текущее время в часовом поясе локации
    active_from_local: Optional[time]  # Начало окна в local timezone
    active_to_local: Optional[time]    # Конец окна в local timezone
    next_allowed_time_utc: Optional[datetime]  # Когда откроется следующее окно (UTC)
    reason: str                   # Объяснение на человеческом языке
```

**Использование**:
```python
result = service.check_schedule(subscription, datetime.now(timezone.utc))

if result.is_allowed:
    # Отправить уведомление сейчас
    send_notification(subscription)
else:
    # Запланировать для pending
    schedule_pending(
        subscription=subscription,
        delivery_at=result.next_allowed_time_utc,
    )
```

### 4. Информация о следующем окне: `NextDeliveryWindow`

```python
@dataclass
class NextDeliveryWindow:
    window_opens_at_utc: datetime   # Когда откроется окно (UTC)
    window_closes_at_utc: datetime  # Когда закроется окно (UTC)
    in_minutes: int                 # Минут до открытия окна
```

**Использование**:
```python
next_window = service.get_next_delivery_window(subscription, now_utc)

if next_window:
    # Запланировать пробуждение
    schedule_wakeup(next_window.window_opens_at_utc)
    logger.info(f"Next window opens in {next_window.in_minutes} minutes")
```

### 5. Исключения

```python
# Основное исключение для сервиса
ScheduleException

# Конкретные ошибки
ScheduleValidationException      # Ошибки валидации расписания
InvalidScheduleFormat            # Format не HH:MM
InvalidTimeWindow                # start_time >= end_time
MissingTimezone                  # Нет timezone у локации
```

## Бизнес-логика

### Timezone вычисления

**Принцип**: Все операции выполняются в timezone локации, результаты возвращаются в UTC.

```
Input:  check_time_utc = 2026-04-09 12:00:00 UTC
                         (UTC timestamp)

        subscription.location.timezone = "Europe/Moscow"

Step 1: Convert to local
        local_time = 2026-04-09 15:00:00 MSK (UTC+3)

Step 2: Compare with window [08:00, 20:00]
        15:00 is within [08:00, 20:00] ✓

Output: result.is_allowed = True
        result.current_time_local = 2026-04-09 15:00:00 MSK
```

### Логика проверки окна

**Алгоритм**:
1. Если `active_from` или `active_to` = NULL → NO_WINDOW (всегда разрешено)
2. Если текущее время (локальное) в пределах `[active_from, active_to)` → ALLOWED
3. Иначе → PENDING_WINDOW_CLOSED (вычисляем next_allowed_time_utc)

**Граничные условия**:
- Начало окна: включено `[active_from` (доставка разрешена)
- Конец окна: исключено `active_to)` (доставка блокирована)
- Пример: `[08:00, 20:00)` = 08:00 до 19:59:59

### Расчет ближайшего допустимого времени

**Логика для PENDING_WINDOW_CLOSED статуса**:

```
Сценарий 1: Время БЫЛО окна открытия
  current_time_local = 07:00 (before 08:00)
  → next_window_opens = today at 08:00 (same day)

Сценарий 2: Время ПОСЛЕ окна закрытия
  current_time_local = 21:00 (after 20:00)
  → next_window_opens = tomorrow at 08:00 (next day)
```

**Конвертация в UTC**:
```python
next_window_local = calculate_local_time(...)
next_window_utc = next_window_local.astimezone(timezone.utc)
```

## Примеры использования

### Базовая проверка расписания

```python
from src.weather_alerts.services.schedule_service import (
    ScheduleService,
    ScheduleStatus,
)

service = ScheduleService()

# Получить подписку из БД
subscription = db.session.get(Subscription, subscription_id)

# Проверить, можно ли отправлять сейчас
result = service.check_schedule(
    subscription=subscription,
    check_time_utc=datetime.now(timezone.utc),
)

# Использовать результат
if result.is_allowed:
    logger.info(f"Delivery allowed: {result.reason}")
    await send_notification(subscription)
else:
    logger.info(f"Delivery pending: {result.reason}")
    await save_pending_notification(
        subscription_id=subscription.id,
        delivery_at=result.next_allowed_time_utc,
    )
```

### Планирование pending-уведомлений

```python
# Когда окно закрыто, получить информацию о следующем окне
next_window = service.get_next_delivery_window(
    subscription=subscription,
    current_time_utc=datetime.now(timezone.utc),
)

if next_window:
    logger.info(
        f"Scheduling pending notification to wake up at "
        f"{next_window.window_opens_at_utc} (in {next_window.in_minutes} min)"
    )
    
    # Сохранить в PendingNotification таблицу
    pending = PendingNotification(
        subscription_id=subscription.id,
        next_delivery_at=next_window.window_opens_at_utc,
        status="pending",
    )
    db.session.add(pending)
    db.session.commit()
```

### Обработка ошибок

```python
from src.weather_alerts.services import (
    InvalidScheduleFormat,
    MissingTimezone,
)

try:
    result = service.check_schedule(subscription, utc_time)
except MissingTimezone:
    logger.error(f"Location {subscription.location_id} has no timezone")
    telemetry.record_error("missing_timezone")
except InvalidScheduleFormat:
    logger.error(f"Invalid schedule in subscription {subscription.id}")
    # Возможно, рекомендовать пользователю проверить настройки
```

### Multi-timezone пример

```python
# Пользователь в Москве (UTC+3)
moscow_sub = Subscription(
    active_from="08:00",
    active_to="20:00",
    location=Location(timezone="Europe/Moscow"),
)

# Пользователь в Токио (UTC+9)
tokyo_sub = Subscription(
    active_from="08:00",
    active_to="20:00",
    location=Location(timezone="Asia/Tokyo"),
)

# Одинаковое время UTC разрешает доставку в разное локальное время
check_time = datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)

moscow_result = service.check_schedule(moscow_sub, check_time)
# Moscow local: 15:00 → ALLOWED (within 08:00-20:00)

tokyo_result = service.check_schedule(tokyo_sub, check_time)
# Tokyo local: 21:00 → PENDING_WINDOW_CLOSED (outside 08:00-20:00)
```

## Структура для unit тестов

Сервис разработан для удобства тестирования:
- **Pure functions**: нет побочных эффектов, явные входы/выходы
- **Explicit timezone handling**: все озвучено в параметрах
- **Mockable time**: метод `_is_utc()` можно расширить для моков
- **Comprehensive test suite**: 32 unit теста (все проходят ✅)

```bash
# Запуск всех тестов
python -m pytest tests/test_schedule_service.py -v

# Результат: 32 passed
```

**Покрытие тестами**:
- ✅ UTC ↔ Local convertations (Moscow, Tokyo, New York)
- ✅ Delivery allowed within window
- ✅ Delivery blocked before/after window
- ✅ Boundary conditions (exactly at start/end, ±1 sec)
- ✅ No window scenarios (NULL active_from, active_to)
- ✅ Time parsing (valid/invalid formats, edge cases)
- ✅ Window validation (start >= end, missing timezone)
- ✅ Next delivery window calculation
- ✅ Result structure and descriptive reasons

## Интеграция с системой

**Где используется**:
1. **Condition Evaluator**: после `ConditionEvaluationService` определяет, доставлять ли сейчас
2. **Orchestrator**: решает, отправить ли уведомление или поставить в pending
3. **Pending Manager**: использует `get_next_delivery_window()` для планирования wake-up

**Входные данные**:
- Subscription с `active_from`, `active_to` (HH:MM или NULL)
- Location с `timezone` (e.g., "Europe/Moscow")
- Current time in UTC

**Выходные данные**:
- `ScheduleCheckResult` с:
  - Boolean `is_allowed` для быстрой проверки
  - Детали `next_allowed_time_utc` для pending
  - Descriptive `reason` для логирования

**Orchestration flow**:
```
1. ConditionEvaluationService.evaluate_subscription()
   → ConditionEvaluationResult (matched=true/false)

2. [если matched==true]
   ScheduleService.check_schedule()
   → ScheduleCheckResult

3. if result.is_allowed:
   deliveryService.send_notification()
   else:
   pendingManager.save_pending(result.next_allowed_time_utc)
```

## Документирование timezone логики

### Как интерпретируются timezone и local time

**1. Прием UTC timestamp**:
```python
check_time_utc = datetime.now(timezone.utc)  # 2026-04-09 12:00:00+00:00
```

**2. Получение timezone локации**:
```python
tz = pytz.timezone(subscription.location.timezone)  # "Europe/Moscow"
```

**3. Конвертация в local time**:
```python
check_time_local = check_time_utc.astimezone(tz)  # 2026-04-09 15:00:00+03:00
```

**4. Сравнение с local window**:
```python
active_from.hour = 8, active_from.minute = 0  # 08:00
active_to.hour = 20, active_to.minute = 0    # 20:00

current_hour = check_time_local.hour  # 15
# 08:00 <= 15:00 < 20:00 ✓ ALLOWED
```

**5. Возврат результатов в UTC**:
```python
next_window_local = ... # 2026-04-10 08:00:00+03:00
next_window_utc = next_window_local.astimezone(timezone.utc)  # 2026-04-10 05:00:00+00:00
```

### Особые случаи

**DST (Daylight Saving Time)**:
- pytz автоматически обрабатывает переходы
- Например, в США 2026-03-09 02:00 EST → 03:00 EDT

**Полуночь и граница дня**:
```python
# Если окно: 08:00 - 20:00
# И текущее время: 21:00 (за границей)
# → Ближайшее окно: ЗАВТРА в 08:00
```

**Нулевые/NULL значения**:
```python
active_from = None  # Нет нижней границы
active_to = "20:00"    # Есть верхняя граница
→ Сообщение: уведомления разрешены ВСЕГДА (игнорируем active_to)
```

## Файлы, измененные/созданные

- ✅ `src/weather_alerts/services/schedule_service.py` (новый, 380+ строк)
- ✅ `tests/test_schedule_service.py` (новый, 32 комплексных теста)
- ✅ `src/weather_alerts/services/exceptions.py` (добавлены schedule исключения)
- ✅ `src/weather_alerts/services/__init__.py` (обновлены экспорты)
- ✅ `artifacts/T015_schedule_service.md` (этот файл с документацией)

## Статистика

- **Строк кода**: ~380 (service + tests ~700)
- **Unit тестов**: 32 (все проходят ✅)
- **Покрытие**: timezone convertations, window checks, boundaries, next window calculation
- **Время выполнения тестов**: <1 сек

## Связь со спецификацией

Сервис реализует следующие требования из spec.md:

- ✅ **FR-007**: Применяет расписание по часовому поясу локации
- ✅ **FR-008**: Переводит уведомление в pending, если событие вне окна доставки
- ✅ **FR-009**: Интерпретирует "дождь завтра" по local timezone (подготовка)

**Используется для будущих задач**:
- T016: Orchestration engine (использует результаты ScheduleService)
- T017: Pending notification manager (использует next_allowed_time_utc)

## Преимущества реализации

1. **Timezone-осознана**: Правильно обрабатывает глобальные пользователей в разных часовых поясах
2. **Testable**: Чистая функция без побочных эффектов
3. **Descriptive results**: Verbose error messages для логирования и отладки
4. **Boundary-safe**: Правильно обрабатывает граничные условия и DST
5. **Orchestration-ready**: Выходы подходят для планирования pending-уведомлений
6. **Well-documented**: Явные комментарии о логике конвертаций

## Следующие шаги

- T016: Orchestration engine (объединяет ConditionEvaluationService + ScheduleService)
- T017: Pending notification manager (использует get_next_delivery_window)
- T018: Деduplication логика (12-часовое окно в рамках деного часового пояса)
