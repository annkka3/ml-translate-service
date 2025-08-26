# app/domain/services/bus.py
from __future__ import annotations

"""
Публикация задач перевода в RabbitMQ.

Особенности:
- Генерирует и возвращает correlation_id (task_id).
- Сообщения помечаются как persistent (delivery_mode=2).
- Объявляет очередь (durable=true) перед публикацией.
- Делает несколько попыток публикации с задержкой.
- Кладёт correlation_id также в payload для удобной идемпотентности воркера.

Использование:
    task_id = publish_task({
        "user_id": "...",
        "input_text": "...",
        "source_lang": "en",
        "target_lang": "fr",
        "model": "marian",
    })
"""

import json
import os
import time
import uuid
from typing import Any, Dict, Optional

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import BasicProperties

# ────────────────────────── SETTINGS ──────────────────────────────────

def _load_settings():
    """Пробуем взять настройки из app.core.settings, иначе — из окружения."""
    try:
        from app.core.settings import get_settings  # type: ignore
        s = get_settings()
        return {
            "AMQP_URL": getattr(s, "AMQP_URL", os.getenv("AMQP_URL", "amqp://guest:guest@localhost:5672/")),
            "TASK_QUEUE": getattr(s, "TASK_QUEUE", os.getenv("TASK_QUEUE", "ml_tasks")),
            "PUBLISH_RETRIES": int(getattr(s, "PUBLISH_RETRIES", os.getenv("PUBLISH_RETRIES", "3"))),
            "PUBLISH_RETRY_DELAY": float(getattr(s, "PUBLISH_RETRY_DELAY", os.getenv("PUBLISH_RETRY_DELAY", "0.5"))),
        }
    except Exception:
        return {
            "AMQP_URL": os.getenv("AMQP_URL", "amqp://guest:guest@localhost:5672/"),
            "TASK_QUEUE": os.getenv("TASK_QUEUE", "ml_tasks"),
            "PUBLISH_RETRIES": int(os.getenv("PUBLISH_RETRIES", "3")),
            "PUBLISH_RETRY_DELAY": float(os.getenv("PUBLISH_RETRY_DELAY", "0.5")),
        }


_cfg = _load_settings()
AMQP_URL: str = _cfg["AMQP_URL"]
TASK_QUEUE: str = _cfg["TASK_QUEUE"]
PUBLISH_RETRIES: int = _cfg["PUBLISH_RETRIES"]
PUBLISH_RETRY_DELAY: float = _cfg["PUBLISH_RETRY_DELAY"]

_params = pika.URLParameters(AMQP_URL)


# ────────────────────────── CORE ──────────────────────────────────────

def _open_channel() -> tuple[pika.BlockingConnection, BlockingChannel]:
    """
    Создаёт соединение и канал; объявляет целевую очередь как durable.
    Возвращает (connection, channel). Закрытие — на вызывающей стороне.
    """
    conn = pika.BlockingConnection(_params)
    ch = conn.channel()
    ch.queue_declare(queue=TASK_QUEUE, durable=True)
    # Опционально можно включить publisher confirms:
    # ch.confirm_delivery()
    return conn, ch


def publish_task(
    payload: Dict[str, Any],
    *,
    correlation_id: Optional[str] = None,
    headers: Optional[Dict[str, Any]] = None,
    retries: Optional[int] = None,
    retry_delay: Optional[float] = None,
) -> str:
    """
    Публикует задачу в очередь TASK_QUEUE и возвращает task_id (correlation_id).

    :param payload: Тело задачи. В него будет добавлено поле "correlation_id".
    :param correlation_id: Задать свой correlation_id (по умолчанию сгенерируем UUID4).
    :param headers: Дополнительные заголовки AMQP-сообщения.
    :param retries: Кол-во повторных попыток при ошибках публикации (по умолчанию из настроек).
    :param retry_delay: Пауза между попытками (сек) (по умолчанию из настроек).
    :return: str task_id
    """
    task_id = correlation_id or str(uuid.uuid4())
    body_dict = {"correlation_id": task_id, **payload}
    body = json.dumps(body_dict, ensure_ascii=False).encode("utf-8")

    _retries = PUBLISH_RETRIES if retries is None else max(0, int(retries))
    _delay = PUBLISH_RETRY_DELAY if retry_delay is None else max(0.0, float(retry_delay))

    props = BasicProperties(
        delivery_mode=2,  # persistent
        correlation_id=task_id,
        content_type="application/json",
        headers=headers or {"attempts": 0},
    )

    last_err: Optional[Exception] = None

    for attempt in range(_retries + 1):
        try:
            conn, ch = _open_channel()
            try:
                ch.basic_publish(
                    exchange="",
                    routing_key=TASK_QUEUE,
                    body=body,
                    properties=props,
                    mandatory=False,  # можно поставить True, если нужен Basic.Return при unroutable
                )
            finally:
                try:
                    ch.close()
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass
            return task_id
        except Exception as e:
            last_err = e
            if attempt < _retries:
                time.sleep(_delay)
            else:
                # исчерпали попытки
                raise

    # формально недостижимо, но чтобы mypy не ругался:
    if last_err:
        raise last_err
    return task_id


__all__ = ["publish_task", "TASK_QUEUE", "AMQP_URL"]
