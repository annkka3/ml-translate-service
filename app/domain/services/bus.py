
import json, os, pika, uuid

AMQP_URL = os.getenv("AMQP_URL", "amqp://guest:guest@localhost:5672/")
TASK_QUEUE = os.getenv("TASK_QUEUE", "ml_tasks")

params = pika.URLParameters(AMQP_URL)

def publish_task(payload: dict) -> str:

    corr_id = str(uuid.uuid4())
    body = json.dumps({"correlation_id": corr_id, **payload}).encode("utf-8")

    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.queue_declare(queue=TASK_QUEUE, durable=True)

    ch.basic_publish(exchange="", routing_key=TASK_QUEUE, body=body,
                     properties=pika.BasicProperties(delivery_mode=2, correlation_id=corr_id))
    conn.close()
    return corr_id
