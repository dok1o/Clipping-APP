"""Job lifecycle: retry policy, backoff, reconcile of stuck jobs (spec §20)."""
import uuid
from datetime import datetime, timedelta, timezone

from app.models.job import Job, JobStatus, JobType
from app.workers.job_lifecycle import (
    IDEMPOTENT_JOB_TYPES,
    backoff_seconds,
    handle_failure,
    handle_success,
    mark_running,
    reconcile_stuck_jobs,
)


def _job(db, job_type=JobType.RENDER, status=JobStatus.RUNNING, attempts=0, updated_ago_min=0):
    job = Job(
        job_type=job_type, ref_type="clip", ref_id=uuid.uuid4(),
        status=status, attempts=attempts, max_attempts=3,
    )
    db.add(job)
    db.commit()
    if updated_ago_min:
        job.updated_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=updated_ago_min)
        db.commit()
    db.refresh(job)
    return job


def test_idempotent_types_only(db) -> None:
    assert JobType.PUBLISH not in IDEMPOTENT_JOB_TYPES
    assert JobType.TRANSCRIBE in IDEMPOTENT_JOB_TYPES
    assert JobType.RENDER in IDEMPOTENT_JOB_TYPES


def test_handle_failure_retrying_then_failed(db) -> None:
    job = _job(db, attempts=0, )  # max_attempts=3
    job, will_retry = handle_failure(db, job.id, "fail 1", allow_retry=True)
    assert will_retry is True and job.status == JobStatus.RETRYING and job.attempts == 1

    job, will_retry = handle_failure(db, job.id, "fail 2", allow_retry=True)
    assert will_retry is True and job.status == JobStatus.RETRYING and job.attempts == 2

    job, will_retry = handle_failure(db, job.id, "fail 3", allow_retry=True)
    assert will_retry is False and job.status == JobStatus.FAILED and job.attempts == 3


def test_handle_failure_publish_never_retries(db) -> None:
    job = _job(db, job_type=JobType.PUBLISH)
    job, will_retry = handle_failure(db, job.id, "platform down", allow_retry=False)
    assert will_retry is False and job.status == JobStatus.FAILED


def test_backoff_exponential() -> None:
    assert backoff_seconds(1) == 60
    assert backoff_seconds(2) == 120
    assert backoff_seconds(3) == 240


def test_reconcile_marks_stuck_running_jobs(db) -> None:
    stuck_render = _job(db, job_type=JobType.RENDER, status=JobStatus.RUNNING, updated_ago_min=30)
    stuck_publish = _job(db, job_type=JobType.PUBLISH, status=JobStatus.RUNNING, updated_ago_min=30)
    fresh = _job(db, status=JobStatus.RUNNING, updated_ago_min=1)
    counts = reconcile_stuck_jobs(db)
    assert counts == {"retrying": 1, "failed": 1}
    db.refresh(stuck_render); db.refresh(stuck_publish); db.refresh(fresh)
    assert stuck_render.status == JobStatus.RETRYING  # idempotent -> retry
    assert stuck_publish.status == JobStatus.FAILED  # publish never retries
    assert fresh.status == JobStatus.RUNNING  # recent job untouched


def test_reconcile_failed_after_max_attempts(db) -> None:
    exhausted = _job(db, job_type=JobType.RENDER, status=JobStatus.RUNNING, attempts=3, updated_ago_min=30)
    counts = reconcile_stuck_jobs(db)
    assert counts["failed"] == 1
    db.refresh(exhausted)
    assert exhausted.status == JobStatus.FAILED


def test_success_and_running_marks(db) -> None:
    job = _job(db, status=JobStatus.QUEUED)
    assert mark_running(db, job.id).status == JobStatus.RUNNING
    finished = handle_success(db, job.id, {"asset_id": "x"})
    assert finished.status == JobStatus.SUCCEEDED
    assert finished.result == {"asset_id": "x"}
    assert finished.finished_at is not None
