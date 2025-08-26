# app/infrastructure/db/config.py
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[3]
ENV_PATH = BASE_DIR / ".env"
if not ENV_PATH.exists():
    ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}


class Settings(BaseSettings):
    # === App ===
    APP_NAME: str = "ML_API"
    APP_VERSION: str = "0.1.0"
    ROOT_PATH: str = ""  # если API висит за префиксом у nginx (например, /api)
    DEBUG: bool = _env_bool("DEBUG", False)
    TESTING: bool = _env_bool("TESTING") or ("PYTEST_CURRENT_TEST" in os.environ)

    # === Security (JWT) ===
    SECRET_KEY: str = "change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # === CORS / Hosts / Metrics ===
    CORS_ALLOW_ORIGINS: str = "*"  # список через запятую
    TRUSTED_HOSTS: str = "*"       # список через запятую
    ENABLE_METRICS: bool = _env_bool("ENABLE_METRICS", True)

    # === Database (async) ===
    DB_HOST: str = "database"
    DB_PORT: int = 5432
    DB_USER: str = "user"
    DB_PASS: str = "password"
    DB_NAME: str = "ml_db"

    # Универсальная асинхронная строка подключения.
    # Поддерживаем оба имени переменной: DATABASE_URL и DATABASE_URL_asyncpg.
    DATABASE_URL: Optional[str] = None
    DATABASE_URL_asyncpg: Optional[str] = None  # alias для совместимости

    DB_ECHO: bool = _env_bool("DB_ECHO", False)

    # === DB Init flags ===
    INIT_DB_ON_START: bool = _env_bool("INIT_DB_ON_START", True)
    INIT_DB_DROP_ALL: bool = _env_bool("INIT_DB_DROP_ALL", False)

    # === AMQP (пусть будут здесь для удобства, даже если воркер читает из app.core.settings) ===
    AMQP_URL: str = os.getenv("AMQP_URL", "amqp://guest:guest@rabbitmq:5672/")
    TASK_QUEUE: str = os.getenv("TASK_QUEUE", "ml_tasks")

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def model_post_init(self, __context) -> None:
        """
        Нормализуем DATABASE_URL:
        1) приоритет у DATABASE_URL (если задана);
        2) затем берём DATABASE_URL_asyncpg (alias);
        3) иначе собираем строку для asyncpg из компонент.
        """
        env_du = (self.DATABASE_URL or "").strip()
        env_du_async = (self.DATABASE_URL_asyncpg or "").strip()

        if env_du:
            # оставляем, как есть
            self.DATABASE_URL = env_du
        elif env_du_async:
            # поддержка alias
            self.DATABASE_URL = env_du_async
        else:
            # собираем по умолчанию
            self.DATABASE_URL = (
                f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            )

        # Тестовое окружение — упрощаем жизнь автотестам
        if self.TESTING:
            self.INIT_DB_ON_START = True
            self.INIT_DB_DROP_ALL = True
            # по желанию можно включить подробный лог SQL
            # self.DB_ECHO = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
