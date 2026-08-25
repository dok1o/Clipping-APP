from __future__ import annotations

import os
from typing import Any

from celery import Celery


CELERY_BROKER_URL_ENV = "CELERY_BROKER_URL"
CELERY_RESULT_BACKEND_ENV = "CELERY_RESULT_BACKEND"
DEFAULT_CELERY_BROKER_URL = "redis://localhost:6379/0"
DEFAULT_CELERY_RESULT_BACKEND = "redis://localhost:6379/1"
HEALTH_CHECK_TASK_NAME = "infra.health_check_task"


def create_celery_app(name: str = "ai_clipper") -> Celery:
    app = Celery(
        name,
        broker=os.environ.get(CELERY_BROKER_URL_ENV, DEFAULT_CELERY_BROKER_URL),
        backend=os.environ.get(CELERY_RESULT_BACKEND_ENV, DEFAULT_CELERY_RESULT_BACKEND),
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
    )
    _register_health_check_task(app)
    return app


def _register_health_check_task(app: Celery) -> None:
    @app.task(name=HEALTH_CHECK_TASK_NAME)
    def health_check_task() -> dict[str, str]:
        return {"status": "ok"}


celery_app = create_celery_app()
health_check_task: Any = celery_app.tasks[HEALTH_CHECK_TASK_NAME]
