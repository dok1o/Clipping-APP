"""Celery application — single place for broker/backend config (ADR-013)."""
from celery import Celery

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def create_celery_app() -> Celery:
    settings = get_settings()
    app = Celery(
        "ai_clipper",
        broker=settings.effective_celery_broker_url,
        backend=settings.redis_url,
        include=["app.workers.tasks"],
    )
    app.conf.update(
        task_always_eager=settings.celery_eager_by_default,
        task_eager_propagates=False,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        broker_connection_retry_on_startup=True,
    )
    logger.debug(
        "celery app created (eager=%s)", settings.celery_eager_by_default
    )
    return app


celery_app = create_celery_app()
