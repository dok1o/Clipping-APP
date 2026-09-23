"""ML training API (Stage 7, spec §3.6)."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.job import Job, JobRefType, JobStatus, JobType
from app.schemas.ml import TrainAccepted, TrainingRunPage, TrainingRunRead
from app.services.ai_clipping import dataset_service

router = APIRouter(tags=["ml"])


@router.post("/ml/train", status_code=202, response_model=TrainAccepted)
def train_model(db: Session = Depends(get_db)) -> TrainAccepted:
    job = Job(
        job_type=JobType.TRAIN,
        ref_type=JobRefType.SYSTEM,
        ref_id=None,
        status=JobStatus.QUEUED,
        payload={},
    )
    db.add(job)
    db.commit()
    from app.workers.tasks import ml_train_task

    ml_train_task.delay(job.id)
    return TrainAccepted(job_id=job.id, status="queued")


@router.get("/ml/runs", response_model=TrainingRunPage)
def list_runs(limit: int = 20, db: Session = Depends(get_db)) -> TrainingRunPage:
    from sqlalchemy import select

    from app.models.training_run import TrainingRun

    rows = list(db.scalars(select(TrainingRun).order_by(TrainingRun.created_at.desc()).limit(min(limit, 100))))
    return TrainingRunPage(items=[TrainingRunRead.model_validate(r) for r in rows], total=len(rows))


@router.get("/ml/active-model")
def active_model(db: Session = Depends(get_db)) -> dict:
    """Active rerank model indicator (None -> heuristic ranking)."""
    from app.services.ai_clipping.ml_ranker import get_active_model

    try:
        loaded = get_active_model(db)
    except Exception:  # noqa: BLE001 — indicator must never break the page
        loaded = None
    if loaded is None:
        return {"active": False, "model_version": None}
    _model, bundle = loaded
    return {
        "active": True,
        "model_version": bundle.get("version"),
        "backend": bundle.get("backend"),
        "feature_keys": bundle.get("feature_keys"),
    }


@router.get("/ml/dataset-status")
def dataset_status(db: Session = Depends(get_db)) -> dict:
    dataset = dataset_service.build_training_dataset(db)
    return {
        "rows": len(dataset.rows),
        "skipped": dataset.skipped,
        "targets": sorted({r.target_kind for r in dataset.rows}),
    }
