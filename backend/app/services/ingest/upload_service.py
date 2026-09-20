"""Video upload: streaming to tmp -> S3 -> Video row (CONTRACTS §4.2, §11)."""
from __future__ import annotations

import re
import tempfile
import uuid
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.infra.s3 import S3Storage
from app.models.video import Video, VideoStatus
from app.services.render.ffmpeg_runner import probe_media

logger = get_logger(__name__)

ALLOWED_MIME = {"video/mp4", "video/quicktime", "video/webm", "video/x-matroska"}
ALLOWED_EXT = {".mp4", ".mov", ".webm", ".mkv"}

CHUNK_SIZE = 1024 * 1024  # 1MB
# multipart overhead allowance before the body is even accepted
MULTIPART_SLACK_BYTES = 2 * 1024 * 1024

_SAFE_RE = re.compile(r"[^a-z0-9._-]+")
_MULTI_DOT_RE = re.compile(r"\.{2,}")
MAX_SAFE_NAME_LEN = 80


def sanitize_filename(name: str) -> str:
    """lower + [a-z0-9._-] + trimmed to 80 chars; deterministic fallback 'video'."""
    base = Path(name or "").name
    lowered = base.lower()
    cleaned = _SAFE_RE.sub("-", lowered)
    cleaned = _MULTI_DOT_RE.sub(".", cleaned)
    cleaned = cleaned.strip(".-")
    if not cleaned:
        cleaned = "video"
    return cleaned[:MAX_SAFE_NAME_LEN]


def build_storage_key(video_id: uuid.UUID, safe_name: str) -> str:
    return f"videos/{video_id}/{safe_name}"


def check_content_length(content_length: int | None, settings: Settings) -> None:
    """413 before reading the body when the declared size already exceeds the limit."""
    if content_length is None:
        return
    limit_bytes = settings.upload_max_mb * 1024 * 1024
    if content_length > limit_bytes + MULTIPART_SLACK_BYTES:
        raise AppError(413, "payload_too_large", f"Upload exceeds {settings.upload_max_mb} MB limit")


def validate_media(filename: str, content_type: str | None) -> None:
    """Mime allowlist + extension check (415 unsupported_media)."""
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise AppError(
            415,
            "unsupported_media",
            "Unsupported file type; allowed: mp4, mov, webm, mkv",
            fields={"filename": filename or ""},
        )
    if content_type is not None:
        mime = content_type.split(";")[0].strip().lower()
        if mime and mime not in ALLOWED_MIME:
            raise AppError(
                415,
                "unsupported_media",
                f"Unsupported content type: {mime}",
                fields={"content_type": mime},
            )


def stream_to_file(fileobj: BinaryIO, tmp_path: Path, settings: Settings) -> int:
    """Copy the upload chunk-by-chunk to a tmp file; enforce the size limit."""
    limit_bytes = settings.upload_max_mb * 1024 * 1024
    total = 0
    while True:
        chunk = fileobj.read(CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > limit_bytes:
            raise AppError(413, "payload_too_large", f"Upload exceeds {settings.upload_max_mb} MB limit")
        with open(tmp_path, "ab") as out:
            out.write(chunk)
    if total == 0:
        raise AppError(400, "empty_file", "Uploaded file is empty")
    return total


def create_video(
    db: Session,
    storage: S3Storage,
    *,
    filename: str,
    content_type: str | None,
    fileobj: BinaryIO,
    settings: Settings,
) -> Video:
    """Full upload flow: validate -> tmp -> S3 -> (optional) ffprobe -> Video ready."""
    validate_media(filename, content_type)

    video_id = uuid.uuid4()
    safe_name = sanitize_filename(filename)
    storage_key = build_storage_key(video_id, safe_name)

    video = Video(
        id=video_id,
        original_filename=filename,
        storage_key=storage_key,
        size_bytes=0,
        mime_type=content_type or _mime_for_ext(safe_name),
        status=VideoStatus.UPLOADING,
    )
    db.add(video)
    db.commit()

    with tempfile.TemporaryDirectory(prefix="clipper-upload-") as tmp_dir:
        tmp_path = Path(tmp_dir) / safe_name
        try:
            size = stream_to_file(fileobj, tmp_path, settings)
            storage.upload_file(tmp_path, storage_key, content_type=video.mime_type)
        except AppError:
            video.status = VideoStatus.FAILED
            video.error_message = "upload rejected"
            db.commit()
            raise
        except Exception as exc:  # noqa: BLE001 — controlled storage error
            logger.exception("storage error during upload")
            video.status = VideoStatus.FAILED
            video.error_message = "storage error"
            db.commit()
            raise AppError(500, "storage_error", "Failed to store the uploaded file") from exc

        # ffprobe is allowed HERE (Video flow); missing binary => metadata stays null
        meta = probe_media(tmp_path)
        video.size_bytes = size
        if meta:
            video.duration_sec = meta["duration_sec"]
            video.width = meta["width"]
            video.height = meta["height"]
        video.status = VideoStatus.READY
        db.commit()
        db.refresh(video)
        return video


def _mime_for_ext(safe_name: str) -> str:
    return {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
    }.get(Path(safe_name).suffix.lower(), "application/octet-stream")
