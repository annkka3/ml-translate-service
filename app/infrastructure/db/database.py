# app/infrastructure/db/database.py
from __future__ import annotations

from typing import AsyncGenerator, Optional

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.infrastructure.db.config import get_settings

settings = get_settings()


# --- Base with naming convention (удобно для Alembic) -----------------
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# --- URL resolver ------------------------------------------------------
def _resolve_database_url() -> str:
    """
    Приоритет:
      1) settings.DATABASE_URL (универсально: sqlite+aiosqlite / postgresql+asyncpg и т.д.)
      2) settings.DATABASE_URL_asyncpg (alias для совместимости)
      3) сборка строки для Postgres (asyncpg) из компонент
    """
    url = (getattr(settings, "DATABASE_URL", None) or "").strip()
    if url:
        return url
    legacy = (getattr(settings, "DATABASE_URL_asyncpg", None) or "").strip()
    if legacy:
        return legacy
    host = getattr(settings, "DB_HOST", "database")
    port = getattr(settings, "DB_PORT", 5432)
    user = getattr(settings, "DB_USER", "user")
    password = getattr(settings, "DB_PASS", "password")
    name = getattr(settings, "DB_NAME", "ml_db")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"


DATABASE_URL: str = _resolve_database_url()


# --- Engine & session factory -----------------------------------------
def _engine() -> AsyncEngine:
    # параметры пула можно задать через окружение/настройки при желании
    pool_size: Optional[int] = getattr(settings, "DB_POOL_SIZE", None)
    max_overflow: Optional[int] = getattr(settings, "DB_MAX_OVERFLOW", None)
    pool_recycle: Optional[int] = getattr(settings, "DB_POOL_RECYCLE", None)  # seconds
    pool_timeout: Optional[int] = getattr(settings, "DB_POOL_TIMEOUT", None)  # seconds

    kwargs = {
        "echo": bool(getattr(settings, "DB_ECHO", False)),
        "pool_pre_ping": True,
        "future": True,
    }
    if pool_size is not None:
        kwargs["pool_size"] = int(pool_size)
    if max_overflow is not None:
        kwargs["max_overflow"] = int(max_overflow)
    if pool_recycle is not None:
        kwargs["pool_recycle"] = int(pool_recycle)
    if pool_timeout is not None:
        kwargs["pool_timeout"] = int(pool_timeout)

    return create_async_engine(DATABASE_URL, **kwargs)


engine: AsyncEngine = _engine()

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# --- FastAPI dependency ------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Выдаёт AsyncSession. Транзакции открывайте локально:
        async with db.begin(): ...
    """
    async with SessionLocal() as session:
        yield session


# --- Optional helpers --------------------------------------------------
async def db_ping(session: AsyncSession) -> bool:
    """
    Быстрый пинг БД для health/ready.
    """
    try:
        await session.execute("SELECT 1")
        return True
    except Exception:
        return False
