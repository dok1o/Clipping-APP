"""Celery tasks — thin wrappers around services (no business logic here).

Retry policy (§20): idempotent types (transcribe/render/text_gen/metrics_sync)
re-dispatch with exponential backoff when a job has attempts left; publish
NEVER auto-retries (duplicate protection via idempotency + external_post_id).
"""
from uuid import UUID

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infra.queue import celery_app
from app.workers.job_lifecycle import (
    backoff_seconds,
    handle_failure,
    handle_success,
    mark_running,
)

logger = get_logger(__name__)


def _run_job(job_id: str, idempotent: bool, body) -> dict:
    """Open session + storage, run `body(db, storage, settings, job)`."""
    from app.api.deps import get_storage
    from app.db.session import session_factory
    from app.infra.s3 import S3Storage

    settings = get_settings()
    db = session_factory()
    storage: S3Storage = get_storage()
    eager = settings.celery_eager_by_default
    try:
        if mark_running(db, UUID(job_id)) is None:
            return {"job_id": job_id, "status": "failed", "error": "job not found"}
        result = body(db, storage, settings)
        # services may finalize the job themselves (e.g. controlled failures);
        # never override a service-level failed status with success
        from app.models.job import Job as _Job

        job = db.get(_Job, UUID(job_id))
        if job is not None and job.status == "failed":
            return {"job_id": job_id, "status": "failed", "result": job.result}
        job = handle_success(db, UUID(job_id), result)
        return {"job_id": job_id, "status": job.status, "result": job.result}
    except Exception as exc:  # noqa: BLE001 — task must not crash the worker
        logger.exception("job %s failed", job_id)
        try:
            _, will_retry = handle_failure(
                db, UUID(job_id), f"{type(exc).__name__}: {exc}", allow_retry=idempotent
            )
        except Exception:  # noqa: BLE001
            will_retry = False
        if will_retry and not eager:
            from app.workers import tasks as _self

            job = db.get(__import__("app.models.job", fromlist=["Job"]).Job, UUID(job_id))
            task = _self._TASK_BY_TYPE.get(job.job_type)
            if task is not None:
                task.apply_async((job_id,), countdown=backoff_seconds(job.attempts + 1))
            return {"job_id": job_id, "status": "retrying"}
        return {"job_id": job_id, "status": "failed", "error": str(exc)[:500]}
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.ping")
def ping() -> str:
    """Technical connectivity task."""
    return "pong"


@celery_app.task(name="app.workers.tasks.render_task")
def render_task(job_id: str | UUID) -> dict:
    from app.services.render.render_service import execute_render_job

    def body(db, storage, _settings):
        job = execute_render_job(db, storage, UUID(str(job_id)))
        return {"asset_id": (job.result or {}).get("asset_id"), "job_status": job.status}

    # render handles its own job state transitions; still route failures through lifecycle
    from app.db.session import session_factory
    from app.services.render.render_service import execute_render_job as exec_render

    db = None
    try:
        db = session_factory()
        job = exec_render(db, _storage(), UUID(str(job_id)))
        return {"job_id": str(job_id), "status": job.status, "result": job.result}
    except Exception as exc:  # noqa: BLE001
        logger.exception("render task failed")
        if db is not None:
            handle_failure(db, UUID(str(job_id)), f"{type(exc).__name__}: {exc}", allow_retry=True)
        return {"job_id": str(job_id), "status": "failed", "error": str(exc)[:500]}
    finally:
        if db is not None:
            db.close()


def _storage():
    from app.api.deps import get_storage

    return get_storage()


@celery_app.task(name="app.workers.tasks.transcribe_task")
def transcribe_task(job_id: str | UUID) -> dict:
    from app.services.transcription.whisper_service import execute_transcription_job

    def body(db, storage, _settings):
        job = execute_transcription_job(db, storage, UUID(str(job_id)))
        return {"job_status": job.status, **(job.result or {})}

    return _run_job(str(job_id), idempotent=True, body=body)


@celery_app.task(name="app.workers.tasks.text_gen_task")
def text_gen_task(job_id: str | UUID, clip_id: str, platform: str, tone: str | None = None,
                  transcript: str | None = None) -> dict:
    from app.services.text_gen.text_service import generate_for_clip as gen

    def body(db, storage, _settings):
        job, _texts = gen(db, clip_id=UUID(clip_id), platform=platform, tone=tone,
                          transcript=transcript)
        return {"job_status": job.status, **(job.result or {})}

    return _run_job(str(job_id), idempotent=True, body=body)


@celery_app.task(name="app.workers.tasks.publish_task")
def publish_task(publication_id: str | UUID) -> dict:
    """Publish a scheduled/manual publication. NEVER auto-retries (§20/§21)."""
    from app.services.publish.publish_service import execute_scheduled_publication

    db = None
    try:
        from app.db.session import session_factory

        db = session_factory()
        publication = execute_scheduled_publication(db, _storage(), UUID(str(publication_id)))
        return {"publication_id": str(publication_id), "status": publication.status,
                "external_post_id": publication.external_post_id}
    except Exception as exc:  # noqa: BLE001
        logger.exception("publish task failed")
        return {"publication_id": str(publication_id), "status": "failed", "error": str(exc)[:500]}
    finally:
        if db is not None:
            db.close()


@celery_app.task(name="app.workers.tasks.metrics_sync_task")
def metrics_sync_task(publication_id: str | UUID) -> dict:
    """Stage 6 implements real metric fetching; stub keeps the contract."""
    return {"publication_id": str(publication_id), "status": "stub"}


@celery_app.task(name="app.workers.tasks.process_scheduled_publications")
def process_scheduled_publications() -> dict:
    """Beat entry (§21): publish due scheduled publications with rate limits."""
    from app.services.publish.publish_service import process_due_publications

    db = None
    try:
        from app.db.session import session_factory

        db = session_factory()
        return process_due_publications(db, _storage())
    except Exception as exc:  # noqa: BLE001
        logger.exception("scheduled publications processing failed")
        return {"error": str(exc)[:500]}
    finally:
        if db is not None:
            db.close()


_TASK_BY_TYPE = {
    "render": render_task,
    "transcribe": transcribe_task,
    "text_gen": text_gen_task,
    "metrics_sync": metrics_sync_task,
}
