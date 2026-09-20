"""Videos API (CONTRACTS §4.2–§4.4)."""
import uuid

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_settings, get_storage
from app.core.errors import AppError
from app.core.logging import get_logger
from app.infra.s3 import S3Storage
from app.models.video import Video
from app.schemas.video import VideoPage, VideoRead
from app.services.ingest import upload_service

logger = get_logger(__name__)
router = APIRouter(prefix="/videos", tags=["videos"])


@router.post("", status_code=201, response_model=VideoRead)
def upload_video(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    storage: S3Storage = Depends(get_storage),
    settings=Depends(get_settings),
) -> Video:
    """Multipart upload (field `file`), streamed to S3; ffprobe metadata optional."""
    raw_length = request.headers.get("content-length")
    try:
        content_length = int(raw_length) if raw_length is not None else None
    except ValueError:
        content_length = None
    upload_service.check_content_length(content_length, settings)

    video = upload_service.create_video(
        db,
        storage,
        filename=file.filename or "",
        content_type=file.content_type,
        fileobj=file.file,
        settings=settings,
    )
    return video


@router.get("", response_model=VideoPage)
def list_videos(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> VideoPage:
    total = db.scalar(select(func.count()).select_from(Video))
    rows = db.scalars(select(Video).order_by(Video.created_at.desc()).limit(limit).offset(offset))
    return VideoPage(items=[VideoRead.model_validate(v) for v in rows], total=total or 0)


@router.get("/{video_id}", response_model=VideoRead)
def get_video(video_id: uuid.UUID, db: Session = Depends(get_db)) -> Video:
    video = db.get(Video, video_id)
    if video is None:
        raise AppError(404, "video_not_found", f"Video {video_id} not found")
    return video
