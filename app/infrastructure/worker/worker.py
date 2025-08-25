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
from app.core.settings import get_settings

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)


settings = get_settings()
AMQP_URL = settings.AMQP_URL
TASK_QUEUE = settings.TASK_QUEUE
DB_URL = settings.DATABASE_URL_asyncpg


APP_PYTHONPATH = os.getenv("APP_PYTHONPATH", "/app_src")
if APP_PYTHONPATH and APP_PYTHONPATH not in sys.path and os.path.isdir(APP_PYTHONPATH):
    sys.path.insert(0, APP_PYTHONPATH)

from app.domain.services.translation_request import process_translation_request  # type: ignore

# ────────────────────────── LOGGING ───────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("worker")

# ────────────────────────── DB (async) ────────────────────────────────
engine = create_async_engine(DB_URL, pool_pre_ping=True, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# ────────────────────────── RABBITMQ ──────────────────────────────────
params = pika.URLParameters(AMQP_URL)
connection: Optional[pika.BlockingConnection] = None
channel: Optional[pika.channel.Channel] = None
running = True


@dataclass
class _InputData:
    input_text: str
    source_lang: str
    target_lang: str


def _extract_task_id(properties: Optional[pika.BasicProperties], payload: Dict[str, Any]) -> str:
    return (
        (properties.correlation_id if properties and properties.correlation_id else None)
        or payload.get("correlation_id")
        or str(uuid.uuid4())
    )


async def _handle_message_async(msg: Dict[str, Any], task_id: str) -> None:
    required = ("user_id", "input_text", "source_lang", "target_lang")
    missing = [k for k in required if k not in msg]
    if missing:
        log.error("task %s invalid payload, missing %s", task_id, missing)
        return
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
            external_id=task_id,  # идемпотентность
        )
        log.info("task %s done: cost=%s", task_id, result.get("cost"))


def _on_message(ch, method, properties, body):
    try:
        msg = json.loads(body.decode("utf-8"))
    except Exception as e:
        log.error("bad message (json decode failed): %s", e)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    task_id = _extract_task_id(properties, msg)
    log.info("received task %s", task_id)

    try:
        asyncio.run(_handle_message_async(msg, task_id))
    except Exception as e:
        log.exception("processing error for task %s: %s", task_id, e)
    finally:
        ch.basic_ack(delivery_tag=method.delivery_tag)


def _consume_loop():
    global connection, channel, running

    while running:
        try:
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            channel.queue_declare(queue=TASK_QUEUE, durable=True)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=TASK_QUEUE, on_message_callback=_on_message)

            log.info("consuming from queue '%s' ...", TASK_QUEUE)
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
    global running
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
