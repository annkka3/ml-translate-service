# app/core/container.py
from __future__ import annotations

from typing import Optional, Callable

from app.infrastructure.db.config import get_settings, Settings
from app.infrastructure.db import database as db

# Подключаем публикацию задач в очередь из доменного сервиса
try:
    from app.domain.services.bus import publish_task as _publish_task
except Exception:
    _publish_task = None  # в среде без RabbitMQ можно оставить None


class Container:
    """
    Простой контейнер зависимостей:
      - settings: конфиг приложения
      - db: модуль с engine/SessionLocal/get_db
      - publish_task: функция публикации задач в RabbitMQ (или None)
    """
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings: Settings = settings or get_settings()
        self.db = db  # .engine, .SessionLocal, .get_db

        # Функция публикации задач (может быть None, если модуль недоступен)
        self.publish_task: Optional[Callable[[dict], str]] = _publish_task

        # Удобные алиасы настроек AMQP (если понадобятся)
        self.amqp_url: str = getattr(self.settings, "AMQP_URL", "amqp://guest:guest@localhost:5672/")
        self.task_queue: str = getattr(self.settings, "TASK_QUEUE", "ml_tasks")

    def has_bus(self) -> bool:
        return callable(self.publish_task)


# Экземпляр контейнера по умолчанию
container = Container()
