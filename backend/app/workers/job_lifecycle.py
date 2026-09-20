"""Shared Celery task lifecycle: running -> succeeded/failed/retrying.

Retry policy (master spec §20): ONLY idempotent job types retry
(transcribe, render, metrics_sync, text_gen). Publish NEVER retries
automatically — duplicates are protected by idempotency keys + external_post_id.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.job import Job, JobStatus, JobType

logger = get_logger(__name__)

IDEMPOTENT_JOB_TYPES = {
    JobType.TRANSCRIBE, JobType.RENDER, JobType.METRICS_SYNC, JobType.TEXT_GEN,
}
STUCK_JOB_MINUTES = 15


def mark_running(db: Session, job_id: uuid.UUID) -> Job | None:
    job = db.get(Job, job_id)
    if job is None:
        return None
    job.status = JobStatus.RUNNING
    job.started_at = job.started_at or datetime.now(timezone.utc)
    db.commit()
    return job


def handle_success(db: Session, job_id: uuid.UUID, result: dict) -> Job:
    job = db.get(Job, job_id)
    job.status = JobStatus.SUCCEEDED
    job.result = result
    job.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job


def handle_failure(
    db: Session, job_id: uuid.UUID, error_message: str, *, allow_retry: bool
) -> tuple[Job, bool]:
    """Returns (job, will_retry): retrying when idempotent AND attempts left."""
    job = db.get(Job, job_id)
    job.error_message = error_message[:2000]
    job.attempts += 1
    will_retry = allow_retry and job.attempts < job.max_attempts
    if will_retry:
        job.status = JobStatus.RETRYING
    else:
        job.status = JobStatus.FAILED
        job.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job, will_retry


def backoff_seconds(attempts: int, base: int = 60, jitter: float = 0.0) -> int:
    """Exponential 2^attempt * base + jitter (spec §21)."""
    import random

    return int((2 ** max(0, attempts - 1)) * base + (jitter * random.random() if jitter else 0))


def reconcile_stuck_jobs(db: Session, stuck_minutes: int = STUCK_JOB_MINUTES) -> dict:
    """Restart recovery (spec §20): running/queued jobs without progress
    for > stuck_minutes become retrying (idempotent) or failed.

    Called on worker startup (worker_ready signal) and available via
    POST /api/v1/jobs/reconcile for manual runs.
    """
    threshold = datetime.now(timezone.utc) - timedelta(minutes=stuck_minutes)
    counts = {"retrying": 0, "failed": 0}
    stuck = db.scalars(
        select(Job).where(
            Job.status.in_([JobStatus.RUNNING, JobStatus.QUEUED]),
            Job.updated_at < threshold.replace(tzinfo=None),
        )
    )
    for job in stuck:
        is_idempotent = job.job_type in IDEMPOTENT_JOB_TYPES
        if is_idempotent and job.attempts < job.max_attempts:
            job.status = JobStatus.RETRYING
            counts["retrying"] += 1
        else:
            job.status = JobStatus.FAILED
            job.error_message = (job.error_message or "") + f" | reconciled: stuck >{stuck_minutes}m"
            job.finished_at = datetime.now(timezone.utc)
            counts["failed"] += 1
    db.commit()
    if any(counts.values()):
        logger.warning("reconcile_stuck_jobs: %s", counts)
    return counts


def requeue_retrying_jobs(db: Session) -> list[uuid.UUID]:
    """Re-dispatch jobs in retrying state (worker startup after reconcile)."""
    from app.workers import tasks as worker_tasks

    job_ids: list[uuid.UUID] = []
    retrying = db.scalars(select(Job).where(Job.status == JobStatus.RETRYING))
    for job in retrying:
        task = _task_for_type(worker_tasks, job.job_type)
        if task is None:
            continue
        countdown = backoff_seconds(job.attempts + 1)
        task.apply_async((str(job.id),), countdown=countdown)
        job_ids.append(job.id)
    if job_ids:
        db.commit()
    return job_ids


def _task_for_type(worker_tasks, job_type: str):
    return {
        JobType.TRANSCRIBE: worker_tasks.transcribe_task,
        JobType.RENDER: worker_tasks.render_task,
        JobType.TEXT_GEN: worker_tasks.text_gen_task,
        JobType.METRICS_SYNC: worker_tasks.metrics_sync_task,
    }.get(job_type)
