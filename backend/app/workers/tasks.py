"""Celery tasks — thin wrappers around services (no business logic here)."""
from app.infra.queue import celery_app


@celery_app.task(name="app.workers.tasks.ping")
def ping() -> str:
    """Technical connectivity task."""
    return "pong"
