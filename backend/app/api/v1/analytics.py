"""Analytics API (CONTRACTS §4.12 Stage 6)."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.analytics import MetricPage, MetricRead, MetricsSyncAccepted
from app.services.analytics import metrics_service

router = APIRouter(tags=["analytics"])


@router.post("/publications/{publication_id}/sync-metrics", status_code=202,
             response_model=MetricsSyncAccepted)
def sync_metrics(publication_id: uuid.UUID, db: Session = Depends(get_db)) -> MetricsSyncAccepted:
    job = metrics_service.queue_metrics_sync(db, publication_id)
    from app.workers.tasks import metrics_sync_task

    metrics_sync_task.delay(job.id)
    return MetricsSyncAccepted(job_id=job.id, publication_id=publication_id, status="queued")


@router.get("/publications/{publication_id}/metrics", response_model=MetricPage)
def get_metrics(publication_id: uuid.UUID, db: Session = Depends(get_db)) -> MetricPage:
    from app.core.errors import AppError
    from app.models.publication import Publication

    if db.get(Publication, publication_id) is None:
        raise AppError(404, "publication_not_found", f"Publication {publication_id} not found")
    rows = metrics_service.list_metrics(db, publication_id)
    return MetricPage(items=[MetricRead.model_validate(m) for m in rows], total=len(rows))
