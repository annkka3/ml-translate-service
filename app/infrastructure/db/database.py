# app/infrastructure/db/database.py
from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.infrastructure.db.config import get_settings

settings = get_settings()


# --- SQLAlchemy Base ---
class Base(DeclarativeBase):
    """Общий declarative Base для всех моделей."""
    pass


def _resolve_database_url() -> str:
    """
    Универсальное определение URL подключения:
    1) settings.DATABASE_URL (новый вариант, универсальный)
    2) settings.DATABASE_URL_asyncpg (старый вариант)
    3) сборка из DB_HOST/DB_PORT/DB_USER/DB_PASS/DB_NAME (фолбэк)
    """
    # 1) новый универсальный URL (sqlite+aiosqlite, postgresql+asyncpg и т.п.)
    url = getattr(settings, "DATABASE_URL", None)
    if url:
        return url

    # 2) обратная совместимость со старым именем
    legacy = getattr(settings, "DATABASE_URL_asyncpg", None)
    if legacy:
        return legacy

    # 3) безопасный дефолт (PostgreSQL + asyncpg)
    host = getattr(settings, "DB_HOST", "database")
    port = getattr(settings, "DB_PORT", 5432)
    user = getattr(settings, "DB_USER", "user")
    password = getattr(settings, "DB_PASS", "password")
    name = getattr(settings, "DB_NAME", "ml_db")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"


# --- DATABASE URL ---
DATABASE_URL = _resolve_database_url()

# --- Engine & sessions ---
engine = create_async_engine(
    DATABASE_URL,
    echo=bool(getattr(settings, "DB_ECHO", False)),
    pool_pre_ping=True,
    future=True,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# --- Dependency ---
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
