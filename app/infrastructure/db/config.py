# app/infrastructure/db/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional
from pathlib import Path
import os

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
    # === Database (fallback parts if DATABASE_URL not provided) ===
    DB_HOST: str = "database"
    DB_PORT: int = 5432
    DB_USER: str = "user"
    DB_PASS: str = "password"
    DB_NAME: str = "ml_db"

    # === App ===
    APP_NAME: str = "ML_API"
    DEBUG: bool = False
    API_VERSION: str = "v1"

    # === Security ===
    SECRET_KEY: str = "change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # === Flags ===
    TESTING: bool = _env_bool("TESTING") or ("PYTEST_CURRENT_TEST" in os.environ)

    # === DB Init flags ===
    INIT_DB_ON_START: bool = True
    INIT_DB_DROP_ALL: bool = False  # безопаснее по умолчанию
    DB_ECHO: bool = False

    # === URLs ===
    # Универсальная асинхронная строка подключения. Если задана переменная окружения
    # DATABASE_URL — используем её. Иначе собираем из компонентов Postgres.
    DATABASE_URL: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def model_post_init(self, __context) -> None:
        # Приоритет: окружение DATABASE_URL (для тестов часто sqlite+aiosqlite)
        if not self.DATABASE_URL or not str(self.DATABASE_URL).strip():
            self.DATABASE_URL = (
                f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            )

        # Если мы в тестах — делаем init и drop безопасно
        if self.TESTING:
            # В автотестах обычно хотим автоинициализацию и чистую схему
            self.INIT_DB_ON_START = True
            # drop_all только в тестовом окружении
            self.INIT_DB_DROP_ALL = True
            # SQLite часто молчит — можно включить echo по желанию:
            # self.DB_ECHO = True

@lru_cache()
def get_settings() -> Settings:
    return Settings()
