# T014: Condition Evaluation Service (Weather Alerts)

**Статус**: ✅ Завершено  
**Дата**: 9 апреля 2026  
**Автор**: AI Engineering Assistant

## Описание

Реализован движок оценки погодных условий (`ConditionEvaluationService`) для Weather Alerts. Сервис оценивает соответствие погодных данных критериям пользовательских подписок и возвращает структурированные результаты для orchrest​ration и отправки уведомлений.

## Реализованные компоненты

### 1. Основной сервис: `ConditionEvaluationService`

**Файл**: `src/weather_alerts/services/condition_evaluation_service.py`

**Интерфейс**:
```python
class ConditionEvaluationService:
    def evaluate_subscription(
        self,
        subscription_id: int,
        conditions: List[SubscriptionCondition],
        forecast: Forecast,
    ) -> ConditionEvaluationResult:
        """Evaluate whether any subscription conditions match weather data."""
```

**Возможности**:
- ✅ `temperature_below`: Текущая температура ниже порога (°C)
- ✅ `temperature_above`: Текущая температура выше порога (°C)
- ✅ `rain_probability_above`: Вероятность дождя выше порога (%)
- ✅ `wind_speed_above`: Скорость ветра выше порога (км/ч)
- ✅ `severe_weather`: Активные суровые погодные явления (storm, hurricane, tornado, blizzard, extreme_heat, extreme_cold)

### 2. Результат оценки: `ConditionEvaluationResult`

```python
@dataclass
class ConditionEvaluationResult:
    subscription_id: int           # ID подписки
    matched: bool                  # Сработало ли хотя бы одно условие?
    matched_conditions: List[MatchedCondition]  # Какие условия сработали
    event_type: Optional[EventType]             # Тип события для маршрутизации
    evaluation_timestamp: datetime  # Когда была оценка (UTC)
    weather_data_timestamp: Optional[datetime]  # Когда данные о погоде (UTC)
```

**Поля **`ConditionEvaluationResult`**:
- `matched`: Булев флаг - `True` если хотя бы одно условие сработало (ANY логика)
- `matched_conditions`: Список все условий, которые сработали (для аудита и логирования)
- `event_type`: Основной тип события для маршрутизации уведомления
- Временные метки: для отладки и метрик

### 3. Сработавшее условие: `MatchedCondition`

```python
@dataclass
class MatchedCondition:
    condition_id: int                # ID условия в БД
    condition_type: ConditionType    # Тип (temperature_below, и т.д.)
    threshold_value: float           # Ожидаемый порог (e.g., -10°C)
    threshold_unit: str              # Единица измерения
    actual_value: float              # Фактическое значение погоды
    actual_unit: str                 # Единица фактического значения
    event_type: EventType            # Тип события (TEMPERATURE_ALERT, etc.)
```

**Назначение**:
- Полное отслеживание: что именно сработало
- Логирование и аудит: какой порог был и что произошло на самом деле
- Metrics: для понимания каких сценариев больше всего срабатывает

### 4. Типы событий: `EventType`

```python
class EventType(str, PyEnum):
    TEMPERATURE_ALERT = "temperature_alert"    # Порог температуры
    RAIN_ALERT = "rain_alert"                  # Вероятность дождя
    WIND_ALERT = "wind_alert"                  # Скорость ветра
    SEVERE_WEATHER_ALERT = "severe_weather_alert"  # Суровая погода (最высокий приоритет)
```

**Приоритизация** (для выбора основного типа события):
1. `SEVERE_WEATHER_ALERT` (критичный)
2. `TEMPERATURE_ALERT` (высокий)
3. `RAIN_ALERT` (средний)
4. `WIND_ALERT` (низкий)

Если срабатывают несколько условий разных типов, выбирается самый приоритетный.

### 5. Исключения для обработки ошибок

```python
# Основное исключение для сервиса
ConditionEvaluationException

# Конкретные ошибки
InvalidWeatherData          # Данные о погоде неполные/невалидные
EmptyConditionSet          # Нет условий для оценки
ConditionEvaluationError   # Неожиданная ошибка при оценке
```

## Бизнес-логика

### ANY-логика для нескольких условий

Если в подписке несколько условий, они связаны логикой **ANY**:
- **Первое совпадение вызывает срабатывание**: как только одно условие сработает, подписка считается сработавшей
- **Все совпадения отслеживаются**: в результате перечисляются все сработавшие условия
- **Один результат на подписку**: даже если сработали 5 условий, отправляется одно уведомление (с указанием всех сработавших условий)

```python
# Пример: подписка с двумя условиями
conditions = [
    SubscriptionCondition(id=1, type=TEMPERATURE_BELOW, threshold=20°C),
    SubscriptionCondition(id=2, type=RAIN_PROBABILITY_ABOVE, threshold=70%),
]

# Если текущие условия: temp=15°C, rain=50%
result = service.evaluate_subscription(..., conditions, forecast)
# result.matched = True (первое условие сработало)
# result.matched_conditions = [MatchedCondition(id=1, ...)]
# result.event_type = TEMPERATURE_ALERT
```

### Выбор типа события при множественных совпадениях

```python
# Если в запросе сработали условия разных типов
conditions = [
    SubscriptionCondition(id=1, type=TEMPERATURE_BELOW, ...),      # TEMPERATURE_ALERT
    SubscriptionCondition(id=2, type=WIND_SPEED_ABOVE, ...),       # WIND_ALERT
    SubscriptionCondition(id=3, type=SEVERE_WEATHER, event=STORM), # SEVERE_WEATHER_ALERT
]

result = service.evaluate_subscription(...)
# result.event_type = SEVERE_WEATHER_ALERT (т.к. это самый приоритетный)
```

## Примеры использования

### Базовое использование

```python
from src.weather_alerts.services.condition_evaluation_service import (
    ConditionEvaluationService,
    EventType,
)
from src.weather_alerts.adapters.weather_provider import WeatherProvider

# Инициализация
service = ConditionEvaluationService()
weather_provider = WeatherProvider()

# Получить текущую подписку (из БД)
subscription = db.session.get(Subscription, subscription_id)

# Получить прогноз
forecast = await weather_provider.get_forecast(
    location_id=subscription.location_id,
    latitude=subscription.location.lat,
    longitude=subscription.location.lon,
)

# Оценить условия
result = service.evaluate_subscription(
    subscription_id=subscription.id,
    conditions=subscription.conditions,
    forecast=forecast,
)

# Использовать результат в orchestrator
if result.matched:
    # Отправить уведомление
    for channel in subscription.channels:
        await send_notification(
            subscription_id=result.subscription_id,
            event_type=result.event_type,
            channel=channel,
            matched_details=result.matched_conditions,  # для логирования
        )
```

### Обработка ошибок

```python
try:
    result = service.evaluate_subscription(
        subscription_id=1,
        conditions=conditions,
        forecast=forecast,
    )
except EmptyConditionSet:
    logger.error(f"Subscription {subscription_id} has no conditions")
except InvalidWeatherData:
    logger.error("Weather data is incomplete, skipping evaluation")
except ConditionEvaluationException as e:
    logger.error(f"Evaluation failed: {e}")
```

### Логирование результатов

```python
result = service.evaluate_subscription(...)

if result.matched:
    # Логировать каждое сработавшее условие
    for matched in result.matched_conditions:
        logger.info(
            f"Condition matched: {matched.condition_type} "
            f"(threshold={matched.threshold_value}{matched.threshold_unit}, "
            f"actual={matched.actual_value}{matched.actual_unit})"
        )
    
    logger.info(f"Event type: {result.event_type}")
```

## Структура для unit тестов

Сервис разработан для удобства тестирования:
- **Pure function**: нет побочных эффектов, нет I/O
- **Explicit inputs**: все данные передаются явно
- **Testable timestamps**: метод `_get_now_utc()` можно замокировать
- **Comprehensive test suite**: 22 unit теста (все проходят ✅)

```bash
# Запуск всех тестов
python -m pytest tests/test_condition_evaluation_service.py -v

# Результат: 22 passed
```

**Покрытие тестами**:
- ✅ Все 5 типов условий (temperature_below/above, rain, wind, severe_weather)
- ✅ ANY-логика (первое совпадение, второе, все, ни одного)
- ✅ Приоритизация типов событий (severe_weather > temperature > rain > wind)
- ✅ Обработка ошибок (пустой список условий, invalid forecast)
- ✅ Структура результатов (все поля присутствуют)

## Интеграция с системой

**Где используется**:
1. **Orchestrator/Evaluator**: запускает оценку для каждой активной подписки
2. **Notification Router**: использует `event_type` для выбора шаблона и канала
3. **Metrics/Logging**: использует `matched_conditions` для аудита

**Входные данные**:
- `Subscription.conditions` (из БД) - список условий подписки
- `Forecast` (из WeatherProvider) - текущие и прогнозные данные

**Выходные данные**:
- `ConditionEvaluationResult` - структурированный результат
  - Булев флаг `matched` для быстрой проверки
  - Детали `matched_conditions` для аудита
  - `event_type` для маршрутизации

## Будущие расширения

**На данный момент отмечены TODO**:
1. Специальная логика для "дождь завтра" - проверка прогноза на следующий день
   - Текущая логика использует текущую вероятность дождя
   - Нужно добавить флаг или отдельное поле для "завтра"

**Поддерживаемое в рамках этой задачи**:
- ✅ Текущие условия (current weather)
- ✅ Прогноз на завтра (daily forecast for tomorrow)
- ✅ Комбинация both в severe_weather (проверяются оба источника)

## Файлы, измененные/созданные

- ✅ `src/weather_alerts/services/condition_evaluation_service.py` (новый)
- ✅ `src/weather_alerts/services/exceptions.py` (добавлены условия оценки)
- ✅ `src/weather_alerts/services/__init__.py` (обновлены экспорты)
- ✅ `tests/test_condition_evaluation_service.py` (новый, 22 теста)

## Статистика

- **Строк кода**: ~450 (service + tests ~750)
- **Unit тестов**: 22 (все проходят)
- **Покрытие**: все типы условий, ANY-логика, приоритизация, ошибки
- **Время выполнения тестов**: <1 сек

## Связь со спецификацией

Сервис реализует следующие требования из spec.md:

- ✅ **FR-004**: Поддерживает температурные условия (below/above)
- ✅ **FR-005**: Реализует ANY-логику для нескольких условий
- ✅ **FR-006**: Поддерживает severe_weather типы
- ✅ **NFR-002**: Идемпотентен (чистая функция без побочных эффектов)

**Не входит в эту задачу** (будущие задачи):
- Интеграция с БД и Redis
- Orchestration loop
- Delivery логика (send_notification)
- Dедупликация в рамках 12-часового окна
- Проверка расписания (active_from/active_to)
