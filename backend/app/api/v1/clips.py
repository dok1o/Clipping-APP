"""Clips API (CONTRACTS §4.5–§4.6)."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import AppError
from app.schemas.rendered_asset import RenderedAssetRead as AssetRead
from app.schemas.clip import ClipCreate, ClipPage, ClipRead, ClipUpdate
from app.schemas.job import JobRead
from app.services.clips import clip_service
from app.services.render import render_service

router = APIRouter(tags=["clips"])


@router.post("/videos/{video_id}/clips/manual", status_code=201, response_model=ClipRead)
def create_manual_clip(video_id: uuid.UUID, payload: ClipCreate, db: Session = Depends(get_db)):
    return clip_service.create_manual_clip(
        db, video_id, title=payload.title, start_sec=payload.start_sec, end_sec=payload.end_sec
    )


@router.get("/clips", response_model=ClipPage)
def list_clips(
    video_id: uuid.UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ClipPage:
    rows, total = clip_service.list_clips(db, video_id, limit, offset)
    return ClipPage(items=[ClipRead.model_validate(c) for c in rows], total=total)


@router.get("/clips/{clip_id}", response_model=ClipRead)
def get_clip(clip_id: uuid.UUID, db: Session = Depends(get_db)):
    return clip_service.get_clip_or_404(db, clip_id)


@router.get("/clips/{clip_id}/asset", response_model=AssetRead)
def get_clip_asset(clip_id: uuid.UUID, db: Session = Depends(get_db)) -> AssetRead:
    """Latest READY rendered asset for the clip (survives page reloads)."""
    from sqlalchemy import select

    from app.models.rendered_asset import RenderedAsset, RenderedAssetStatus

    clip_service.get_clip_or_404(db, clip_id)
    asset = db.scalars(
        select(RenderedAsset)
        .where(
            RenderedAsset.clip_id == clip_id,
            RenderedAsset.status == RenderedAssetStatus.READY,
        )
        .order_by(RenderedAsset.created_at.desc())
        .limit(1)
    ).first()
    if asset is None:
        raise AppError(404, "asset_not_found", "Clip has no ready rendered asset")
    return asset


@router.patch("/clips/{clip_id}", response_model=ClipRead)
def patch_clip(
    clip_id: uuid.UUID, payload: ClipUpdate, db: Session = Depends(get_db)
) -> ClipRead:
    return clip_service.update_clip(
        db, clip_id,
        title=payload.title,
        start_sec=payload.start_sec,
        end_sec=payload.end_sec,
    )


@router.post("/clips/{clip_id}/render", status_code=202, response_model=JobRead)
def render_clip(clip_id: uuid.UUID, db: Session = Depends(get_db)) -> JobRead:
    """Queue a vertical render (CONTRACTS §4.7). Eager Celery runs it in-process in dev/tests."""
    job, clip_status = render_service.queue_render(db, clip_id)
    if clip_status == "render_queued":
        from app.workers.tasks import render_task

        render_task.delay(job.id)
    return JobRead.model_validate(job)
