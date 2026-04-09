# T011: REST API Routes для управления подписками

**Date:** 2025-04-10  
**Task:** Implement REST API routes for subscription management  
**Status:** ✅ Complete

## Overview

Реализованы REST API endpoints для управления подписками Weather Alerts с полным маппингом доменных исключений на HTTP статусы, правильной документацией и местом для future auth.

## Files Created

### 1. `src/weather_alerts/api/routes/subscriptions.py` (450+ lines)

Полный набор endpoints с OpenAPI документацией:

#### Endpoints (7 total)

| Метод | Endpoint | Описание | Status |
|-------|----------|---------|--------|
| POST | `/alerts/subscriptions` | Создать подписку | 201 Created |
| GET | `/alerts/subscriptions` | Список подписок | 200 OK |
| GET | `/alerts/subscriptions/{id}` | Получить подписку | 200 OK |
| PATCH | `/alerts/subscriptions/{id}` | Обновить подписку | 200 OK |
| DELETE | `/alerts/subscriptions/{id}` | Удалить подписку | 204 No Content |
| POST | `/alerts/subscriptions/{id}/pause` | Отключить подписку | 200 OK |
| POST | `/alerts/subscriptions/{id}/resume` | Включить подписку | 200 OK |

#### POST /alerts/subscriptions - Создание

```python
@router.post(
    "",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_subscription(
    request: CreateSubscriptionRequest,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user),
) -> SubscriptionResponse:
```

**Status codes:**
- `201 Created`: Успешное создание
- `400 Bad Request`: Некорректное расписание, неправильные данные
- `409 Conflict`: Активная подписка уже существует (user + location)
- `422 Unprocessable Entity`: Неподдерживаемый тип условия/канала

**Пример запроса:**
```json
{
  "location": { "id": 1 },
  "conditions": [
    {"type": "rain_probability_above", "threshold_value": 70}
  ],
  "schedule": {
    "timezone_source": "location",
    "active_from": "08:00",
    "active_to": "20:00"
  },
  "delivery_channels": [
    {"type": "email", "destination": "user@example.com", "active": true}
  ]
}
```

#### GET /alerts/subscriptions - Список

```python
@router.get(
    "",
    response_model=List[SubscriptionResponse],
    status_code=status.HTTP_200_OK
)
async def list_subscriptions(
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> List[SubscriptionResponse]:
```

**Status codes:**
- `200 OK`: Список подписок (может быть пусто)

**Query parameters:**
- `limit`: Макс 100 элементов (default), макс 1000
- `offset`: Пропустить N элементов (pagination)

**Инвариант:** Возвращает только status != DELETED (soft-delete фильтрация)

#### GET /alerts/subscriptions/{id} - Получить

```python
@router.get(
    "/{subscription_id}",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_200_OK
)
async def get_subscription(
    subscription_id: int = Path(..., ge=1),
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user),
) -> SubscriptionResponse:
```

**Status codes:**
- `200 OK`: Полная подписка
- `403 Forbidden`: Пользователь не владеет подпиской
- `404 Not Found`: Подписка не найдена

#### PATCH /alerts/subscriptions/{id} - Обновить

```python
@router.patch(
    "/{subscription_id}",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_200_OK
)
async def update_subscription(
    request: UpdateSubscriptionRequest,
    subscription_id: int = Path(..., ge=1),
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user),
) -> SubscriptionResponse:
```

**Status codes:**
- `200 OK`: Обновленная подписка
- `400 Bad Request`: Некорректные данные
- `403 Forbidden`: Не владеет подпиской
- `404 Not Found`: Не найдена
- `409 Conflict`: Нельзя обновлять deleted подписку

**Partial update семантика:**
```json
# Пример 1: Обновить только расписание
{
  "schedule": {
    "active_from": "09:00",
    "active_to": "18:00"
  }
}
// conditions и channels сохраняются!

# Пример 2: Заменить все условия
{
  "conditions": [
    {"type": "temperature_below", "threshold_value": -15}
  ]
}
// Старые условия удаляются, создаются новые
```

#### DELETE /alerts/subscriptions/{id} - Удалить

```python
@router.delete(
    "/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
async def delete_subscription(
    subscription_id: int = Path(..., ge=1),
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user),
) -> None:
```

**Status codes:**
- `204 No Content`: Успешно удалена (пустое тело response)
- `403 Forbidden`: Не владеет подпиской
- `404 Not Found`: Не найдена
- `409 Conflict`: Уже удалена

**Soft-delete:**
- status = "deleted"
- deleted_at = current timestamp
- Data preserved в БД

#### POST /alerts/subscriptions/{id}/pause - Отключить

```python
@router.post(
    "/{subscription_id}/pause",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_200_OK
)
async def pause_subscription(
    subscription_id: int = Path(..., ge=1),
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user),
) -> SubscriptionResponse:
```

**Status codes:**
- `200 OK`: Подписка отключена (status=disabled)
- `403 Forbidden`: Не владеет подпиской
- `404 Not Found`: Не найдена
- `409 Conflict`: Уже disabled или deleted

**Состояние переход:** ACTIVE → DISABLED

#### POST /alerts/subscriptions/{id}/resume - Включить

```python
@router.post(
    "/{subscription_id}/resume",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_200_OK
)
async def resume_subscription(
    subscription_id: int = Path(..., ge=1),
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user),
) -> SubscriptionResponse:
```

**Status codes:**
- `200 OK`: Подписка включена (status=active)
- `403 Forbidden`: Не владеет подпиской
- `404 Not Found`: Не найдена
- `409 Conflict`: Уже active или deleted

**Состояние переход:** DISABLED → ACTIVE

### 2. `src/weather_alerts/api/routes/__init__.py` (10 lines)

Экспортирует router:
```python
from .subscriptions import router as subscriptions_router

__all__ = ["subscriptions_router"]
```

### 3. `src/weather_alerts/api/main.py` (100+ lines)

FastAPI app factory с:
- Routes registration
- Startup/shutdown events (init_db, close_db)
- Health check endpoint
- Exception handler для uncaught errors

```python
def create_app() -> FastAPI:
    app = FastAPI(title="Weather Alerts API", ...)
    
    @app.on_event("startup")
    async def startup_event():
        await init_db()
    
    @app.on_event("shutdown")
    async def shutdown_event():
        await close_db()
    
    app.include_router(subscriptions_router)
    
    @app.get("/health")
    async def health_check():
        return {"status": "ok"}
    
    return app

app = create_app()
```

**Run:**
```bash
uvicorn src.weather_alerts.api.main:app --reload
```

### 4. `src/weather_alerts/api/__init__.py` (updated)

Экспортирует app и create_app:
```python
from .main import app, create_app

__all__ = ["app", "create_app"]
```

## Маппинг Исключений → HTTP Status

### Exception Mapping Function

```python
def _handle_service_error(error: Exception) -> None:
    """Convert service exceptions to HTTP responses."""
    
    if isinstance(error, SubscriptionNotFound):
        raise HTTPException(404, detail=str(error))
    
    elif isinstance(error, UnauthorizedSubscriptionAccess):
        raise HTTPException(403, detail=str(error))
    
    elif isinstance(error, SubscriptionAlreadyExists):
        raise HTTPException(409, detail=str(error))
    
    elif isinstance(error, (
        SubscriptionAlreadyDeleted,
        SubscriptionAlreadyDisabled,
        SubscriptionAlreadyActive
    )):
        raise HTTPException(409, detail=str(error))
    
    elif isinstance(error, InvalidSubscriptionData):
        raise HTTPException(400, detail=str(error))
    
    else:
        raise HTTPException(500, detail="Internal server error")
```

### Таблица Маппинга

| Доменное исключение | HTTP Status | Значение |
|-------------------|-------------|----------|
| SubscriptionNotFound | 404 | Subscription doesn't exist |
| UnauthorizedSubscriptionAccess | 403 | User not authorized for this subscription |
| SubscriptionAlreadyExists | 409 | Subscription already exists for user+location |
| SubscriptionAlreadyDeleted | 409 | Cannot update/delete already deleted |
| SubscriptionAlreadyDisabled | 409 | Cannot pause already disabled |
| SubscriptionAlreadyActive | 409 | Cannot resume already active |
| InvalidSubscriptionData | 400 | Invalid request data |

## Authentication Placeholder

```python
async def get_current_user() -> str:
    """Extract current user from request context.
    
    TODO: Implement OAuth2/JWT token validation.
    For now, returns hardcoded user for testing.
    
    Future implementation:
    1. Extract Bearer token from Authorization header
    2. Validate JWT signature and expiration
    3. Extract user_id from payload
    4. Raise HTTPException(403) if invalid
    """
    return "test_user_123"  # Hardcoded for testing
```

**Future auth implementation** (для заполнения в T012 или позже):
```python
from fastapi.security import HTTPBearer, HTTPAuthCredential
import jwt

async def get_current_user(
    credentials: HTTPAuthCredential = Depends(HTTPBearer())
) -> str:
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(403, "Invalid token")
        return user_id
    except JWTError:
        raise HTTPException(403, "Invalid token")
```

## OpenAPI Integration

Все endpoints имеют:
- **summary**: Краткое описание
- **description**: Детальное описание с примерами
- **responses**: Документация возможных status codes
- **request/response models**: Pydantic schemas
- **path/query parameters**: С типами и валидацией

### Docs URLs
- Swagger UI: `GET /docs`
- ReDoc: `GET /redoc`
- OpenAPI JSON: `GET /openapi.json`

## Примеры Использования

### Создание подписки (curl)
```bash
curl -X POST http://localhost:8000/alerts/subscriptions \
  -H "Content-Type: application/json" \
  -d '{
    "location": {"id": 1},
    "conditions": [{"type": "rain_probability_above", "threshold_value": 70}],
    "delivery_channels": [{"type": "email", "destination": "user@example.com"}]
  }'

# Response: 201 Created
{
  "id": 1,
  "user_id": "test_user_123",
  "status": "active",
  "conditions": [...],
  "delivery_channels": [...],
  "created_at": "2025-04-10T10:00:00Z"
}
```

### Список подписок с пагинацией
```bash
curl http://localhost:8000/alerts/subscriptions?limit=10&offset=0

# Response: 200 OK
[
  {"id": 1, "status": "active", ...},
  {"id": 2, "status": "disabled", ...}
]
```

### Обновить только расписание
```bash
curl -X PATCH http://localhost:8000/alerts/subscriptions/1 \
  -H "Content-Type: application/json" \
  -d '{
    "schedule": {
      "active_from": "09:00",
      "active_to": "18:00"
    }
  }'

# Response: 200 OK
# (conditions и channels не изменяются)
```

### Отключить подписку
```bash
curl -X POST http://localhost:8000/alerts/subscriptions/1/pause

# Response: 200 OK
{"id": 1, "status": "disabled", ...}
```

### Удалить подписку
```bash
curl -X DELETE http://localhost:8000/alerts/subscriptions/1

# Response: 204 No Content
# (пустое тело)
```

## Интеграция Stack

**Request → Response Flow:**

```
HTTP Request
    ↓
FastAPI route handler
    ↓
Dependency injection:
  - get_db_session() → AsyncSession
  - get_current_user() → str (user_id)
    ↓
Pydantic validation:
  - CreateSubscriptionRequest (POST body)
  - UpdateSubscriptionRequest (PATCH body)
    ↓
SubscriptionService method
    ↓
Domain exception (if error):
  - SubscriptionNotFound
  - UnauthorizedSubscriptionAccess
  - InvalidSubscriptionData
  - etc.
    ↓
_handle_service_error() mapping
    ↓
HTTPException(status_code, detail)
    ↓
HTTP Response
  - Status code (200/201/204/400/403/404/409)
  - Body (JSON or empty)
  - Headers
```

## Инварианты Роутов

### 1. AUTHORIZATION
```
Каждый route проверяет: subscription.user_id == request.user_id
```

### 2. STATUS CODES
```
201 Created   → POST успех
200 OK        → GET/PATCH/POST (pause/resume) успех
204 No Content → DELETE успех (пустое тело)
400 Bad Request → Invalid data
403 Forbidden → Unauthorized access
404 Not Found → Resource missing
409 Conflict → State conflict (already deleted/disabled/active)
```

### 3. RESPONSE BODIES
```
201: Full SubscriptionResponse (with ID)
200: Full SubscriptionResponse or relevant model
204: No content (пустое)
400/403/404/409: {"detail": "error message"}
```

### 4. PATH PARAMETERS
```
ge=1: Все ID > 0
Path(..., ge=1, description="..."): Валидация на уровне OpenAPI
```

### 5. QUERY PARAMETERS
```
limit: 1-1000 (default 100)
offset: >= 0
```

## Следующие Шаги

- **T012:** Main app setup с:
  - Exception handlers (already in main.py)
  - CORS middleware
  - Request/response logging
  - Error monitoring (Sentry, etc.)
  
- **T013+:** Auth реализация (OAuth2)

- **Phase 3:** Weather evaluation, delivery channels

## Dependencies

- **fastapi** (0.104.1): Web framework
- **sqlalchemy** (2.0+): Async ORM
- **pydantic** (v2.5.0+): Request/response validation
- **uvicorn** (0.24+): ASGI server (for running)

## Files Modified
- Created: `src/weather_alerts/api/routes/subscriptions.py`
- Created: `src/weather_alerts/api/routes/__init__.py`
- Created: `src/weather_alerts/api/main.py`
- Updated: `src/weather_alerts/api/__init__.py`

