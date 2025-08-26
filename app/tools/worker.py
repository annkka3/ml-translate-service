# app/tools/worker.py
from __future__ import annotations

import json
import logging
import signal
import time
from typing import Any, Optional

import pika

from app.core.settings import get_settings

settings = get_settings()

# ---------------------- logging ----------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("tools.worker")

# ---------------------- config -----------------------
AMQP_URL: str = getattr(settings, "AMQP_URL", "amqp://guest:guest@localhost:5672/")
TASK_QUEUE: str = getattr(settings, "TASK_QUEUE", "ml_tasks")

# Поведение по умолчанию для ретраев
MAX_CONNECT_ATTEMPTS: int = int(getattr(settings, "WORKER_CONNECT_ATTEMPTS", 30))
RETRY_DELAY_SEC: float = float(getattr(settings, "WORKER_RETRY_DELAY_SEC", 2.0))
PREFETCH_COUNT: int = int(getattr(settings, "WORKER_PREFETCH", 1))

_running = True
_connection: Optional[pika.BlockingConnection] = None
_channel: Optional[pika.adapters.blocking_connection.BlockingChannel] = None


def _handle_sigterm(*_: Any) -> None:
    global _running, _channel
    log.info("signal received, stopping consumer...")
    _running = False
    try:
        if _channel and _channel.is_open:
            _channel.stop_consuming()
    except Exception:
        pass


signal.signal(signal.SIGINT, _handle_sigterm)
signal.signal(signal.SIGTERM, _handle_sigterm)


# ---------------------- task processor ----------------------
def process_task(payload: dict[str, Any], *, correlation_id: Optional[str]) -> None:
    """
    Простейший обработчик: логирует полученную задачу.
    Поменяй реализацию под свои нужды (например, дернуть доменный сервис).
    """
    log.info(
        "task %s: %s",
        correlation_id or "-",
        json.dumps(payload, ensure_ascii=False),
    )


# ---------------------- RabbitMQ I/O ------------------------
def _connect_with_retries(params: pika.URLParameters) -> pika.BlockingConnection:
    last_exc: Optional[BaseException] = None
    for attempt in range(1, MAX_CONNECT_ATTEMPTS + 1):
        try:
            conn = pika.BlockingConnection(params)
            log.info("connected to RabbitMQ on attempt %d", attempt)
            return conn
        except pika.exceptions.AMQPConnectionError as e:
            last_exc = e
            log.warning(
                "RabbitMQ not ready (attempt %d/%d): %s",
                attempt,
                MAX_CONNECT_ATTEMPTS,
                e,
            )
            time.sleep(RETRY_DELAY_SEC)
    raise RuntimeError(f"RabbitMQ is not reachable after {MAX_CONNECT_ATTEMPTS} attempts") from last_exc


def _safe_json(body: bytes) -> dict[str, Any]:
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        # возвращаем «сырой» текст в структурированном виде
        return {"raw": body.decode("utf-8", errors="replace")}


def _on_message(ch, method, properties, body: bytes) -> None:
    routing_key = getattr(method, "routing_key", TASK_QUEUE)
    corr_id = getattr(properties, "correlation_id", None)
    try:
        payload = _safe_json(body)
        log.info("received message rk=%s corr=%s", routing_key, corr_id or "-")
        process_task(payload, correlation_id=corr_id)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        # для отладочного воркера — подтверждаем, чтобы не зацикливать
        log.exception("failed to process message corr=%s: %s", corr_id or "-", e)
        ch.basic_ack(delivery_tag=method.delivery_tag)


def _consume_once() -> None:
    global _connection, _channel

    params = pika.URLParameters(AMQP_URL)
    _connection = _connect_with_retries(params)
    _channel = _connection.channel()

    # гарантируем очередь (durable)
    _channel.queue_declare(queue=TASK_QUEUE, durable=True)
    _channel.basic_qos(prefetch_count=PREFETCH_COUNT)
    _channel.basic_consume(queue=TASK_QUEUE, on_message_callback=_on_message)

    log.info("listening queue '%s' (prefetch=%d)...", TASK_QUEUE, PREFETCH_COUNT)
    try:
        _channel.start_consuming()
    finally:
        try:
            if _channel and _channel.is_open:
                _channel.close()
        except Exception:
            pass
        try:
            if _connection and _connection.is_open:
                _connection.close()
        except Exception:
            pass


def main() -> None:
    global _running
    log.info("tools worker starting (queue=%s)", TASK_QUEUE)
    while _running:
        try:
            _consume_once()
        except Exception as e:
            if not _running:
                break
            log.error("consumer error: %s (reconnect in %.1fs)", e, RETRY_DELAY_SEC)
            time.sleep(RETRY_DELAY_SEC)
    log.info("worker stopped")


if __name__ == "__main__":
    main()
