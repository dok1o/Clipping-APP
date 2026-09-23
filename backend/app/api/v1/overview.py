"""Overview API (CONTRACTS §4.14): one aggregate call for the home dashboard."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.clip import Clip
from app.models.job import Job
from app.models.publication import Publication, PublicationStatus
from app.models.video import Video
from app.schemas.overview import OverviewStats

router = APIRouter(tags=["overview"])


def _counts(db: Session, column, model) -> dict[str, int]:
    rows = db.execute(select(column, func.count()).group_by(column)).all()
    return {status: count for status, count in rows}


@router.get("/overview", response_model=OverviewStats)
def get_overview(db: Session = Depends(get_db)) -> OverviewStats:
    now = datetime.now(timezone.utc)

    videos = _counts(db, Video.status, Video)
    clips = _counts(db, Clip.status, Clip)
    jobs = _counts(db, Job.status, Job)
    publications = _counts(db, Publication.status, Publication)

    scheduled_next = db.scalar(
        select(func.min(Publication.scheduled_at)).where(
            Publication.status == PublicationStatus.SCHEDULED
        )
    )
    failed_recent = db.scalar(
        select(func.count()).select_from(Job).where(
            Job.status == "failed",
            Job.created_at >= (now - timedelta(hours=24)).replace(tzinfo=None),
        )
    ) or 0

    # latest metric snapshot per published publication (single pass over metrics)
    from sqlalchemy import Integer, cast

    from app.models.metric import Metric

    latest = db.execute(
        select(
            func.count(func.distinct(Metric.publication_id)),
            func.coalesce(func.sum(Metric.views), 0),
            func.coalesce(func.sum(Metric.likes), 0),
            func.coalesce(func.sum(Metric.comments), 0),
            func.coalesce(func.sum(Metric.shares), 0),
        ).where(
            Metric.id.in_(
                select(func.max(Metric.id)).group_by(Metric.publication_id)
            )
        )
    ).one()
    latest_metrics = {
        "publications": latest[0] or 0,
        "views": int(latest[1] or 0),
        "likes": int(latest[2] or 0),
        "comments": int(latest[3] or 0),
        "shares": int(latest[4] or 0),
    }

    from app.services.ai_clipping import dataset_service
    from app.services.ai_clipping.ml_ranker import get_active_model

    dataset_rows = len(dataset_service.build_training_dataset(db))
    try:
        active = get_active_model(db)
    except Exception:  # noqa: BLE001 — indicator must never break the page
        active = None
    ml = {"dataset_rows": dataset_rows, "active_model": None}
    if active is not None:
        _model, bundle = active
        ml["active_model"] = {
            "model_version": bundle.get("version"),
            "backend": bundle.get("backend"),
        }

    return OverviewStats(
        videos=videos,
        clips=clips,
        jobs=jobs,
        publications=publications,
        scheduled_next_at=scheduled_next.isoformat() if scheduled_next else None,
        failed_jobs_recent=failed_recent,
        latest_metrics=latest_metrics,
        ml=ml,
    )
