"""Celery tasks — thin wrappers around services (no business logic here)."""
from uuid import UUID

from app.core.logging import get_logger
from app.infra.queue import celery_app

logger = get_logger(__name__)


def _run_with_session(fn) -> dict:
    """Open a DB session + storage for the task body (shared helper)."""
    from app.api.deps import get_storage
    from app.core.config import get_settings
    from app.db.session import session_factory
    from app.infra.s3 import S3Storage

    settings = get_settings()
    db = session_factory()
    storage: S3Storage = get_storage()  # dependency function is plain callable
    try:
        result = fn(db, storage, settings)
        return result
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.ping")
def ping() -> str:
    """Technical connectivity task."""
    return "pong"


@celery_app.task(name="app.workers.tasks.render_task")
def render_task(job_id: str | UUID) -> dict:
    """Render a queued job (thin wrapper; lifecycle lives in render_service)."""
    from app.services.render.render_service import execute_render_job

    job_id = str(job_id)

    def body(db, storage, _settings):
        job = execute_render_job(db, storage, UUID(job_id))
        return {"job_id": job_id, "status": job.status, "result": job.result}

    try:
        return _run_with_session(body)
    except Exception as exc:  # noqa: BLE001 — task must not crash the worker
        logger.exception("render task failed")
        return {"job_id": job_id, "status": "failed", "error": str(exc)[:500]}
