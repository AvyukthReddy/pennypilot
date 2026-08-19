from celery import Celery

from app.core.config import settings

celery_client = Celery("pennypilot-backend", broker=settings.redis_url)


def enqueue_parse_statement(statement_id: str, signed_url: str) -> None:
    celery_client.send_task("worker.parse_statement", args=[statement_id, signed_url])
