"""Transcripts API (CONTRACTS §4.12 Stage 3)."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.transcription import TranscriptPage, TranscriptSegmentRead, TranscribeAccepted
from app.services.transcription import whisper_service

router = APIRouter(tags=["transcripts"])


@router.post("/videos/{video_id}/transcribe", status_code=202, response_model=TranscribeAccepted)
def transcribe_video(video_id: uuid.UUID, db: Session = Depends(get_db)) -> TranscribeAccepted:
    job = whisper_service.queue_transcription(db, video_id)
    from app.workers.tasks import transcribe_task

    transcribe_task.delay(job.id)
    return TranscribeAccepted(job_id=job.id, video_id=video_id, status="queued")


@router.get("/videos/{video_id}/transcript", response_model=TranscriptPage)
def get_transcript(
    video_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> TranscriptPage:
    from app.core.errors import AppError
    from app.models.transcript import TranscriptSegment
    from app.models.video import Video

    if db.get(Video, video_id) is None:
        raise AppError(404, "video_not_found", f"Video {video_id} not found")
    total = db.scalar(
        select(func.count()).select_from(TranscriptSegment).where(TranscriptSegment.video_id == video_id)
    )
    rows = db.scalars(
        select(TranscriptSegment)
        .where(TranscriptSegment.video_id == video_id)
        .order_by(TranscriptSegment.start)
        .limit(limit)
        .offset(offset)
    )
    return TranscriptPage(
        items=[TranscriptSegmentRead.model_validate(s) for s in rows], total=total or 0
    )
