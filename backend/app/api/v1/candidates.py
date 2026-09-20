"""Candidates API (CONTRACTS §4.12 Stage 3)."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_storage
from app.infra.s3 import S3Storage
from app.models.clip_candidate import ClipCandidate
from app.schemas.ai_clipping import CandidatePage, CandidateRead, PromoteRequest
from app.schemas.clip import ClipRead
from app.services.ai_clipping import candidate_service

router = APIRouter(tags=["candidates"])


@router.post("/videos/{video_id}/candidates", response_model=CandidatePage)
def generate_candidates(
    video_id: uuid.UUID,
    top_k: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
    storage: S3Storage = Depends(get_storage),
) -> CandidatePage:
    rows, ranked_by = candidate_service.generate_candidates(db, storage, video_id, top_k=top_k)
    return CandidatePage(
        items=[CandidateRead.model_validate(c) for c in rows], total=len(rows), ranked_by=ranked_by
    )


@router.get("/videos/{video_id}/candidates", response_model=CandidatePage)
def list_candidates(
    video_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> CandidatePage:
    total = db.scalar(
        select(func.count()).select_from(ClipCandidate).where(ClipCandidate.video_id == video_id)
    )
    rows = db.scalars(
        select(ClipCandidate)
        .where(ClipCandidate.video_id == video_id)
        .order_by(ClipCandidate.score.desc())
        .limit(limit)
        .offset(offset)
    )
    return CandidatePage(items=[CandidateRead.model_validate(c) for c in rows], total=total or 0)


@router.post("/candidates/{candidate_id}/promote", status_code=201, response_model=ClipRead)
def promote_candidate(
    candidate_id: uuid.UUID, payload: PromoteRequest | None = None, db: Session = Depends(get_db)
):
    title = payload.title if payload else None
    return candidate_service.promote_candidate(db, candidate_id, title)
