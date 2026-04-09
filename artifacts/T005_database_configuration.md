# T005: Подключение к базе данных (Database Configuration)

## Созданный файл

**`src/weather_alerts/config/database.py`** (140+ строк) — асинхронное подключение к PostgreSQL с SQLAlchemy 2.x

## Ключевые компоненты

### 1. Base (DeclarativeBase)

```python
from src.weather_alerts.config import Base

class Subscription(Base):
    __tablename__ = "subscriptions"
    # ...
```

**Назначение**: Базовый класс для всех ORM моделей. Все модели должны наследоваться от `Base`.

### 2. Async Engine

```python
engine = get_engine()
```

**Конфигурация**:
- Driver: `postgresql+asyncpg://` (асинхронный)
- Pool size: 20 (из settings)
- Max overflow: 10 (из settings)
- pool_pre_ping: True (проверяет соединения перед использованием)

### 3. Session Factory

```python
session_factory = get_session_factory()
async with session_factory() as session:
    # работа с БД
```

**Особенности**:
- AsyncSession (асинхронная сессия)
- expire_on_commit=False (объекты остаются валидными после commit)
- autoflush=False (ручное управление flush)
- autocommit=False (явный commit)

### 4. FastAPI Dependency (get_db_session)

```python
from fastapi import Depends
from sqlalchemy import select
from src.weather_alerts.config import get_db_session

@app.get("/subscriptions")
async def list_subscriptions(session: AsyncSession = Depends(get_db_session)):
    result = await session.execute(select(Subscription))
    return result.scalars().all()
```

**Особенности**:
- Автоматический commit при успехе
- Автоматический rollback при ошибке
- Автоматическое закрытие сессии в finally блоке

## Использование в коде

### В FastAPI маршрутах

```python
from fastapi import FastAPI, Depends
from sqlalchemy import select
from src.weather_alerts.config import get_db_session

@app.post("/subscriptions")
async def create_subscription(
    data: SubscriptionCreate,
    session: AsyncSession = Depends(get_db_session)
):
    subscription = Subscription(**data.dict())
    session.add(subscription)
    # Commit происходит автоматически в get_db_session
    return subscription
```

### В CLI или тестах (прямое использование)

```python
from sqlalchemy import select
from src.weather_alerts.config import get_session_factory

async def list_all_subscriptions():
    session_factory = get_session_factory()
    async with session_factory() as session:
        stmt = select(Subscription)
        result = await session.execute(stmt)
        return result.scalars().all()
```

## Жизненный цикл приложения

### В main.py (FastAPI app)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.weather_alerts.config import init_db, close_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()  # Создать таблицы (при первом запуске)
    yield
    # Shutdown
    await close_db()  # Закрыть все соединения

app = FastAPI(lifespan=lifespan)
```

**Примечание**: `init_db()` создает таблицы один раз. Для production используйте Alembic миграции вместо `init_db()`.

## Функции

| Функция | Назначение |
|---------|-----------|
| **get_engine()** | Получить или создать async engine (ленивая инициализация) |
| **get_session_factory()** | Получить или создать session factory |
| **get_db_session()** | FastAPI dependency для внедрения сессии в маршруты |
| **init_db()** | Создать все таблицы (используется при startup) |
| **close_db()** | Закрыть все соединения (используется при shutdown) |

## Соответствие DATABASE_URL

Все параметры берутся из `src.weather_alerts.config.settings`:

```python
settings = get_settings()
db_url = settings.db.url  # postgresql+asyncpg://weather_user:weather_pass@localhost:5432/weather_alerts
pool_size = settings.db.pool_size  # 20
```

## SQLAlchemy 2.x особенности

✅ **Async-first**: используются `create_async_engine`, `AsyncSession`, `async_sessionmaker`  
✅ **Type hints**: полная поддержка типов  
✅ **Modern style**: `select()` вместо Query API  
✅ **Explicit transactions**: ручное управление commit/rollback  

## Пример создания модели

```python
# in src/weather_alerts/domain/models/subscription.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, EnumAsString
from src.weather_alerts.config import Base

class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False)
    location_id = Column(Integer, nullable=False)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
```

## Следующие шаги

- T006: Реализовать Redis client и utilities
- T007: Создать ORM модели (Subscription, SubscriptionCondition, DeliveryChannel)
- T008: Alembic миграции для initial schema
