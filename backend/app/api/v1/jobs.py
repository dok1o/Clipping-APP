"""Jobs API (CONTRACTS §4.10)."""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import AppError
from app.models.job import Job
from app.schemas.job import JobRead

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: UUID, db: Session = Depends(get_db)) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise AppError(404, "job_not_found", f"Job {job_id} not found")
    return job


@router.post("/reconcile")
def reconcile_jobs(db: Session = Depends(get_db)) -> dict:
    """Manual stuck-job reconciliation (runs automatically on worker start)."""
    from app.workers.job_lifecycle import reconcile_stuck_jobs, requeue_retrying_jobs

    counts = reconcile_stuck_jobs(db)
    requeued = requeue_retrying_jobs(db)
    return {"reconciled": counts, "requeued": len(requeued)}
