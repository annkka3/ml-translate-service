from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # === App ===
    APP_NAME: str = "ML_API"
    DEBUG: bool = False
    INIT_DB_ON_START: bool = False
    INIT_DB_DROP_ALL: bool = False  # опционально: жёсткая инициализация в dev

    # === Auth ===
    SECRET_KEY: str = "change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # === DB ===
    DB_HOST: str = "database"
    DB_PORT: int = 5432
    DB_USER: str = "user"
    DB_PASS: str = "password"
    DB_NAME: str = "ml_db"
    DATABASE_URL_asyncpg: str | None = None

    # === RabbitMQ / Worker ===
    AMQP_URL: str = "amqp://user:pass@rabbitmq:5672/"
    TASK_QUEUE: str = "ml_tasks"

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        env_file=".env",
    )

    def model_post_init(self, __context) -> None:
        if not self.DATABASE_URL_asyncpg:
            self.DATABASE_URL_asyncpg = (
                f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            )

@lru_cache
def get_settings() -> "Settings":
    return Settings()
