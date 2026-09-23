"""Jobs API (CONTRACTS §4.10, §4.13)."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import AppError
from app.models.job import Job
from app.schemas.job import JobPage, JobRead

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobPage)
def list_jobs(
    status: str | None = Query(default=None, max_length=16),
    type: str | None = Query(default=None, max_length=16, alias="type"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> JobPage:
    """Newest first; optional status/type filters (dashboard queue + failures)."""
    query = select(Job).order_by(Job.created_at.desc(), Job.id)
    count_query = select(func.count()).select_from(Job)
    if status:
        query = query.where(Job.status == status)
        count_query = count_query.where(Job.status == status)
    if type:
        query = query.where(Job.job_type == type)
        count_query = count_query.where(Job.job_type == type)
    total = db.scalar(count_query) or 0
    rows = list(db.scalars(query.offset(offset).limit(limit)))
    return JobPage(items=rows, total=total)


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
