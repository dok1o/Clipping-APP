"""Worker CLI entry point: celery -A app.workers.celery_app worker

On startup (worker_ready) stuck jobs are reconciled and retrying jobs
are re-dispatched (master spec §20).
"""
from celery.signals import worker_ready

from app.infra.queue import celery_app

__all__ = ["celery_app"]


@worker_ready.connect
def _reconcile_on_start(**_kwargs):  # pragma: no cover - signal wiring, logic unit-tested
    from app.db.session import session_factory
    from app.workers.job_lifecycle import reconcile_stuck_jobs, requeue_retrying_jobs

    try:
        db = session_factory()
        try:
            counts = reconcile_stuck_jobs(db)
            requeued = requeue_retrying_jobs(db)
            print(f"[worker] reconcile: {counts}, requeued: {len(requeued)}")
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001 - never crash the worker on startup hooks
        print(f"[worker] reconcile failed: {exc}")
