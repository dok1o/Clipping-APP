from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import PurePath
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.infra.config import UploadSettings, get_upload_settings
from app.infra.database import get_session
from app.infra.models import Clip, Video
from app.infra.storage import ObjectStorage, get_object_storage
from app.ingestion.schemas import ClipCreate, ClipResponse, VideoResponse


router = APIRouter(prefix="/videos", tags=["videos"])
clip_router = APIRouter(prefix="/clips", tags=["clips"])

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
VIDEO_CREATED_STATUS = "uploaded"
CLIP_CREATED_STATUS = "created"


@router.post("", response_model=VideoResponse, status_code=status.HTTP_201_CREATED)
def upload_video(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    storage: ObjectStorage = Depends(get_object_storage),
    upload_settings: UploadSettings = Depends(get_upload_settings),
) -> Video:
    _validate_upload(file, upload_settings.video_upload_max_bytes)

    video_id = uuid4()
    safe_filename = _safe_filename(file.filename or "video")
    storage_key = f"videos/{video_id}/{safe_filename}"
    now = datetime.now(UTC)
    video = Video(
        id=video_id,
        source_path=None,
        storage_key=storage_key,
        original_filename=file.filename or safe_filename,
        status=VIDEO_CREATED_STATUS,
        created_at=now,
    )

    try:
        file.file.seek(0)
        storage.upload_fileobj(file.file, storage_key, content_type=file.content_type)
        session.add(video)
        session.commit()
        session.refresh(video)
    except Exception:
        session.rollback()
        raise

    return video


@router.get("/{video_id}", response_model=VideoResponse)
def get_video(video_id: UUID, session: Session = Depends(get_session)) -> Video:
    return _get_video_or_404(video_id, session)


@router.post("/{video_id}/clips", response_model=ClipResponse, status_code=status.HTTP_201_CREATED)
def create_clip(video_id: UUID, payload: ClipCreate, session: Session = Depends(get_session)) -> Clip:
    _get_video_or_404(video_id, session)
    clip = Clip(
        id=uuid4(),
        video_id=video_id,
        start=Decimal(str(payload.start)),
        end=Decimal(str(payload.end)),
        status=CLIP_CREATED_STATUS,
        created_at=datetime.now(UTC),
    )

    try:
        session.add(clip)
        session.commit()
        session.refresh(clip)
    except Exception:
        session.rollback()
        raise

    return clip


@router.get("/{video_id}/clips", response_model=list[ClipResponse])
def list_video_clips(video_id: UUID, session: Session = Depends(get_session)) -> list[Clip]:
    video = _get_video_or_404(video_id, session)
    return list(video.clips)


@clip_router.get("/{clip_id}", response_model=ClipResponse)
def get_clip(clip_id: UUID, session: Session = Depends(get_session)) -> Clip:
    clip = session.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")
    return clip


def _validate_upload(file: UploadFile, max_bytes: int) -> None:
    filename = file.filename or ""
    extension = PurePath(filename).suffix.lower()
    if extension not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported video extension")
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported media type")

    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)

    if size <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
    if size > max_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Uploaded file is too large")


def _safe_filename(filename: str) -> str:
    name = PurePath(filename).name
    return name or "video"


def _get_video_or_404(video_id: UUID, session: Session) -> Video:
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    return video
