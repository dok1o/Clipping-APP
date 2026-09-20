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
        beat_schedule={
            "process-scheduled-publications": {
                "task": "app.workers.tasks.process_scheduled_publications",
                "schedule": 30.0,  # every 30s (spec §21: Beat preferable)
            },
            "sync-all-metrics": {
                "task": "app.workers.tasks.sync_all_metrics",
                "schedule": 900.0,  # every 15 min (spec §22: периодический sync)
            },
            "self-train-check": {
                "task": "app.workers.tasks.self_train_check",
                "schedule": 21600.0,  # every 6h (spec §3.6: отдельный этап самообучения)
            },
        },
    )
    logger.debug(
        "celery app created (eager=%s)", settings.celery_eager_by_default
    )
    return app


celery_app = create_celery_app()
