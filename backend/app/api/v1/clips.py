"""Clips API (CONTRACTS §4.5–§4.6)."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.clip import ClipCreate, ClipPage, ClipRead
from app.services.clips import clip_service

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
