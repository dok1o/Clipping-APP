from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePath
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.infra.config import UploadSettings, get_upload_settings
from app.infra.database import get_session
from app.infra.models import Video
from app.infra.storage import ObjectStorage, get_object_storage
from app.ingestion.schemas import VideoResponse


router = APIRouter(prefix="/videos", tags=["videos"])

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
VIDEO_CREATED_STATUS = "uploaded"


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
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    return video


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
