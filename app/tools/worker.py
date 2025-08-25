import json
import pika
import time
from typing import Any, Callable

from app.core.settings import get_settings

settings = get_settings()


def process_task(body: bytes) -> None:
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        data = {"raw": body.decode("utf-8", errors="replace")}
    print("[worker] got task:", data)


def main() -> None:
    params = pika.URLParameters(settings.AMQP_URL)

    for attempt in range(1, 31):
        try:
            conn = pika.BlockingConnection(params)
            break
        except pika.exceptions.AMQPConnectionError:
            print(f"[worker] waiting RabbitMQ... ({attempt}/30)")
            time.sleep(2)
    else:
        raise RuntimeError("RabbitMQ is not reachable")

    ch = conn.channel()
    ch.queue_declare(queue=settings.TASK_QUEUE, durable=True)

    def _callback(ch_, method, properties, body):
        process_task(body)
        ch_.basic_ack(delivery_tag=method.delivery_tag)

    ch.basic_qos(prefetch_count=1)
    ch.basic_consume(queue=settings.TASK_QUEUE, on_message_callback=_callback)

    print(f"[worker] listening queue {settings.TASK_QUEUE} ...")
    try:
        ch.start_consuming()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
