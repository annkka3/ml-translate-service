# app/infrastructure/worker/worker.py
import os
import sys
import json
import time
import uuid
import asyncio
import signal
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)

# ────────────────────────── SETTINGS ──────────────────────────────────
# важный момент: PYTHONPATH для доступа к исходникам внутри контейнера
APP_PYTHONPATH = os.getenv("APP_PYTHONPATH", "/app_src")
if APP_PYTHONPATH and APP_PYTHONPATH not in sys.path and os.path.isdir(APP_PYTHONPATH):
    sys.path.insert(0, APP_PYTHONPATH)

# настройки (оставляем импорт из вашего проекта)
from app.core.settings import get_settings  # noqa: E402
from app.domain.services.translation_request import process_translation_request  # noqa: E402

settings = get_settings()
AMQP_URL = settings.AMQP_URL
TASK_QUEUE = settings.TASK_QUEUE
DB_URL = settings.DATABASE_URL_asyncpg
MAX_RETRIES = int(getattr(settings, "WORKER_MAX_RETRIES", 5))
RETRY_DELAY_SEC = float(getattr(settings, "WORKER_RETRY_DELAY_SEC", 1.0))
FAILED_QUEUE = f"{TASK_QUEUE}.failed"

# ────────────────────────── LOGGING ───────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("worker")

# ────────────────────────── DB (async) ────────────────────────────────
engine = create_async_engine(DB_URL, pool_pre_ping=True, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# ────────────────────────── RABBITMQ ──────────────────────────────────
params = pika.URLParameters(AMQP_URL)
connection: Optional[pika.BlockingConnection] = None
channel: Optional[BlockingChannel] = None
running = True


@dataclass
class _InputData:
    input_text: str
    source_lang: str
    target_lang: str


def _extract_task_id(properties: Optional[BasicProperties], payload: Dict[str, Any]) -> str:
    """
    Достаёт correlation_id из свойств или из payload,
    иначе генерирует новый UUID (на всякий случай).
    """
    return (
        (properties.correlation_id if properties and properties.correlation_id else None)
        or payload.get("correlation_id")
        or str(uuid.uuid4())
    )


def _get_attempts(properties: Optional[BasicProperties]) -> int:
    """
    Считает число попыток обработки из headers['attempts'].
    Для requeue через nack брокер не меняет headers, поэтому
    мы используем стратегию ack + republish с инкрементом attempts.
    """
    try:
        if properties and properties.headers and "attempts" in properties.headers:
            return int(properties.headers["attempts"])
    except Exception:
        pass
    return 0


def _publish_retry(ch: BlockingChannel, payload: Dict[str, Any], task_id: str, attempts: int) -> None:
    """
    Пере-публикует сообщение в очередь с увеличенным attempts.
    Используем тот же correlation_id для идемпотентности.
    """
    props = BasicProperties(
        delivery_mode=2,  # persistent
        correlation_id=task_id,
        headers={"attempts": attempts},
        content_type="application/json",
    )
    ch.basic_publish(
        exchange="",
        routing_key=TASK_QUEUE,
        properties=props,
        body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        mandatory=False,
    )


def _publish_failed(ch: BlockingChannel, payload: Dict[str, Any], task_id: str, attempts: int) -> None:
    """
    Отправляет невосстановимое сообщение в failed-очередь.
    """
    # гарантируем наличие failed-очереди
    ch.queue_declare(queue=FAILED_QUEUE, durable=True)
    props = BasicProperties(
        delivery_mode=2,
        correlation_id=task_id,
        headers={"attempts": attempts, "failed": True},
        content_type="application/json",
    )
    ch.basic_publish(
        exchange="",
        routing_key=FAILED_QUEUE,
        properties=props,
        body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        mandatory=False,
    )


async def _handle_message_async(msg: Dict[str, Any], task_id: str) -> None:
    """
    Основная асинхронная обработка: валидация входа → доменная функция обработки.
    """
    required = ("user_id", "input_text", "source_lang", "target_lang")
    missing = [k for k in required if k not in msg]
    if missing:
        raise ValueError(f"invalid payload, missing {missing}")

    user_id = str(msg["user_id"]).strip()
    data = _InputData(
        input_text=str(msg["input_text"]),
        source_lang=str(msg["source_lang"]),
        target_lang=str(msg["target_lang"]),
    )

    async with SessionLocal() as db:
        result = await process_translation_request(
            db=db,
            user_id=user_id,
            data=data,
            external_id=task_id,  # идемпотентность: одна задача — одна запись
        )
        log.info("task %s done: cost=%s", task_id, result.get("cost"))


def _on_message(ch: BlockingChannel, method: Basic.Deliver, properties: BasicProperties, body: bytes):
    """
    Callback потребителя. Управляет ack/republish, ограничивает количество попыток.
    """
    received_at = time.time()
    try:
        msg = json.loads(body.decode("utf-8"))
    except Exception as e:
        log.error("bad message (json decode failed): %s", e)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    task_id = _extract_task_id(properties, msg)
    attempts = _get_attempts(properties)
    log.info("received task %s (attempt %d)", task_id, attempts + 1)

    try:
        # Запускаем асинхронную обработку синхронно в этом потоке
        asyncio.run(_handle_message_async(msg, task_id))
        ch.basic_ack(delivery_tag=method.delivery_tag)
        proc_ms = int((time.time() - received_at) * 1000)
        log.info("ack task %s in %dms", task_id, proc_ms)
    except Exception as e:
        log.exception("processing error for task %s: %s", task_id, e)
        # стратегия: ack + republish (с тем же correlation_id) до MAX_RETRIES
        try:
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception:
            # если ack не удался — пробуем закрыть канал/соединение; сообщение будет redelivered брокером
            pass

        if attempts + 1 < MAX_RETRIES:
            time.sleep(RETRY_DELAY_SEC)
            try:
                _publish_retry(ch, msg, task_id, attempts + 1)
                log.warning("republished task %s (attempt %d/%d)", task_id, attempts + 1, MAX_RETRIES)
            except Exception:
                log.exception("failed to republish task %s", task_id)
        else:
            try:
                _publish_failed(ch, msg, task_id, attempts + 1)
                log.error("task %s moved to failed queue after %d attempts", task_id, attempts + 1)
            except Exception:
                log.exception("failed to publish task %s to failed queue", task_id)


def _consume_loop():
    """
    Основной цикл: подключение → объявление очередей → потребление.
    Автовосстановление соединения с бэкоффом.
    """
    global connection, channel, running

    while running:
        try:
            connection = pika.BlockingConnection(params)
            channel = connection.channel()

            # основной рабочий queue
            channel.queue_declare(queue=TASK_QUEUE, durable=True)
            # очередь для неудачных задач (используем при исчерпании попыток)
            channel.queue_declare(queue=FAILED_QUEUE, durable=True)

            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=TASK_QUEUE, on_message_callback=_on_message)

            log.info("consuming from queue '%s' (failed='%s') ...", TASK_QUEUE, FAILED_QUEUE)
            channel.start_consuming()

        except Exception as e:
            if running:
                log.error("connection error: %s (reconnect in 3s)", e)
                time.sleep(3)
        finally:
            try:
                if channel and channel.is_open:
                    channel.close()
            except Exception:
                pass
            try:
                if connection and connection.is_open:
                    connection.close()
            except Exception:
                pass


def _handle_sigterm(*_):
    """
    Корректное завершение по сигналам.
    """
    global running, channel
    running = False
    try:
        if channel and channel.is_open:
            channel.stop_consuming()
    except Exception:
        pass


def main():
    signal.signal(signal.SIGINT, _handle_sigterm)
    signal.signal(signal.SIGTERM, _handle_sigterm)
    _consume_loop()


if __name__ == "__main__":
    main()
