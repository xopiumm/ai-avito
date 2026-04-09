"""Database connection and session management for Weather Alerts service.

SQLAlchemy 2.x async-first approach with asyncpg driver.
"""

from typing import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.weather_alerts.config.settings import get_settings


class Base(DeclarativeBase):
    """Base class for all ORM models.
    
    All domain models must inherit from this class to be recognized by SQLAlchemy.
    """

    pass


# Global engine and session factory instances
_engine = None
_async_session_factory = None


def get_engine():
    """Get or create async database engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.db.url,
            echo=settings.db.echo,
            pool_size=settings.db.pool_size,
            max_overflow=settings.db.max_overflow,
            pool_pre_ping=True,  # Test connections before use
            connect_args={
                "timeout": 10,
                "server_settings": {
                    "application_name": "weather_alerts",
                },
            },
        )
    return _engine


def get_session_factory():
    """Get or create async session factory."""
    global _async_session_factory
    if _async_session_factory is None:
        engine = get_engine()
        _async_session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,  # Don't expire objects after commit
            autoflush=False,  # Manual flush control
            autocommit=False,
        )
    return _async_session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency provider for FastAPI to inject DB session into routes.
    
    Usage in FastAPI routes:
        @app.get("/subscriptions")
        async def list_subscriptions(session: AsyncSession = Depends(get_db_session)):
            result = await session.execute(select(Subscription))
            return result.scalars().all()
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            # Auto-commit on successful completion
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database (create all tables).
    
    Call this once during application startup if using non-Alembic approach.
    For production, use Alembic migrations instead.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        # Create all tables defined in Base.metadata
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections.
    
    Call this during application shutdown.
    """
    global _engine, _async_session_factory
    
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    
    _async_session_factory = None


# Example usage patterns (for reference, not executed)
"""
# In FastAPI app startup/main.py:
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from sqlalchemy import select
from src.weather_alerts.config.database import (
    get_db_session, 
    init_db, 
    close_db,
    Base
)
from src.weather_alerts.domain.models.subscription import Subscription

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    yield
    # Shutdown
    await close_db()

app = FastAPI(lifespan=lifespan)

# Using dependency injection in routes:
@app.get("/subscriptions")
async def list_subscriptions(session: AsyncSession = Depends(get_db_session)):
    stmt = select(Subscription).limit(10)
    result = await session.execute(stmt)
    subscriptions = result.scalars().all()
    return subscriptions

# Direct session usage (for tests or CLI):
async def get_all_subscriptions():
    session_factory = get_session_factory()
    async with session_factory() as session:
        stmt = select(Subscription)
        result = await session.execute(stmt)
        return result.scalars().all()
"""
