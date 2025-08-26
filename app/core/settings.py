# app/core/settings.py
from __future__ import annotations

import os
from functools import lru_cache
from typing import TypeAlias

from app.infrastructure.db.config import (
    get_settings as _base_get_settings,
    Settings as _BaseSettings,
)

# публичный тип — такой же, как базовый
Settings: TypeAlias = _BaseSettings

def _build_amqp_url() -> str:
    # собираем из окружения (совместимо с docker-compose)
    user = os.getenv("RABBITMQ_USER", "user")
    pwd = os.getenv("RABBITMQ_PASSWORD", "password")
    host = os.getenv("RABBITMQ_HOST", "rabbitmq")
    port = os.getenv("RABBITMQ_PORT", "5672")
    return os.getenv("AMQP_URL", f"amqp://{user}:{pwd}@{host}:{port}/")

@lru_cache()
def get_settings() -> Settings:
    """
    Возвращает единый объект настроек из infrastructure/db/config.py
    + добавляет недостающие поля (AMQP_URL, TASK_QUEUE) и алиасы для обратной совместимости.
    """
    s = _base_get_settings()

    # --- AMQP / очередь (если их нет в базовых настройках)
    if not hasattr(s, "AMQP_URL") or not getattr(s, "AMQP_URL"):
        setattr(s, "AMQP_URL", _build_amqp_url())
    if not hasattr(s, "TASK_QUEUE") or not getattr(s, "TASK_QUEUE"):
        setattr(s, "TASK_QUEUE", os.getenv("TASK_QUEUE", "ml_tasks"))

    # --- совместимость: если кто-то ждёт DATABASE_URL_asyncpg
    if not getattr(s, "DATABASE_URL_asyncpg", None):
        # если базовые настройки уже собрали DATABASE_URL — используем его
        if getattr(s, "DATABASE_URL", None):
            setattr(s, "DATABASE_URL_asyncpg", s.DATABASE_URL)

    return s
