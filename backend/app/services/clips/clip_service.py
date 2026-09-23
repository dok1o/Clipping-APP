"""Manual clip creation — timestamp validation only (CONTRACTS §4.5, §12).

No media binaries are executed in this flow: they are slow and
video.duration_sec may be null (the spec forbids eager media checks here).
"""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.clip import Clip, ClipStatus
from app.models.video import Video, VideoStatus


def get_video_or_404(db: Session, video_id: UUID) -> Video:
    video = db.get(Video, video_id)
    if video is None:
        raise AppError(404, "video_not_found", f"Video {video_id} not found")
    return video


def create_manual_clip(
    db: Session, video_id: UUID, *, title: str, start_sec: float, end_sec: float
) -> Clip:
    settings = get_settings()
    video = get_video_or_404(db, video_id)

    if video.status != VideoStatus.READY:
        raise AppError(409, "video_not_ready", f"Video {video_id} is not ready (status={video.status})")

    if end_sec <= start_sec:
        raise AppError(
            400, "invalid_range", "end_sec must be greater than start_sec",
            fields={"start_sec": str(start_sec), "end_sec": str(end_sec)},
        )

    duration = end_sec - start_sec
    if duration < settings.clip_min_sec:
        raise AppError(
            400, "clip_too_short",
            f"Clip must be at least {settings.clip_min_sec} seconds (got {duration:.2f})",
            fields={"duration_sec": f"{duration:.2f}"},
        )
    if duration > settings.clip_max_sec:
        raise AppError(
            400, "clip_too_long",
            f"Clip must be at most {settings.clip_max_sec} seconds (got {duration:.2f})",
            fields={"duration_sec": f"{duration:.2f}"},
        )

    # duration known in DB => end must not exceed it; unknown => skip (no media binary check)
    if video.duration_sec is not None and end_sec > float(video.duration_sec):
        raise AppError(
            400, "invalid_range",
            f"end_sec exceeds video duration ({video.duration_sec}s)",
            fields={"end_sec": str(end_sec), "video_duration_sec": str(video.duration_sec)},
        )

    clip = Clip(
        video_id=video_id,
        title=title,
        start_sec=start_sec,
        end_sec=end_sec,
        status=ClipStatus.DRAFT,
    )
    db.add(clip)
    db.commit()
    db.refresh(clip)
    return clip


def update_clip(
    db: Session,
    clip_id: UUID,
    *,
    title: str | None = None,
    start_sec: float | None = None,
    end_sec: float | None = None,
) -> Clip:
    """Edit a DRAFT clip (title/timecodes). Rendered clips are immutable."""
    from app.models.clip import ClipStatus

    clip = get_clip_or_404(db, clip_id)
    if clip.status != ClipStatus.DRAFT:
        raise AppError(
            409, "clip_not_editable", f"Only draft clips can be edited (status={clip.status})"
        )
    settings = get_settings()
    new_start = start_sec if start_sec is not None else clip.start_sec
    new_end = end_sec if end_sec is not None else clip.end_sec
    if new_end <= new_start:
        raise AppError(400, "invalid_range", "end_sec must be greater than start_sec")
    duration = new_end - new_start
    if duration < settings.clip_min_sec or duration > settings.clip_max_sec:
        raise AppError(
            400, "invalid_clip_state",
            f"Clip must be {settings.clip_min_sec}-{settings.clip_max_sec} seconds "
            f"(got {duration:.2f})",
        )
    if new_start < 0:
        raise AppError(400, "invalid_range", "start_sec must be >= 0")
    if title is not None:
        clip.title = title
    clip.start_sec = new_start
    clip.end_sec = new_end
    db.commit()
    db.refresh(clip)
    return clip


def get_clip_or_404(db: Session, clip_id: UUID) -> Clip:
    clip = db.get(Clip, clip_id)
    if clip is None:
        raise AppError(404, "clip_not_found", f"Clip {clip_id} not found")
    return clip


def list_clips(db: Session, video_id: UUID | None, limit: int, offset: int) -> tuple[list[Clip], int]:
    from sqlalchemy import func

    query = select(Clip)
    count_query = select(func.count()).select_from(Clip)
    if video_id is not None:
        query = query.where(Clip.video_id == video_id)
        count_query = count_query.where(Clip.video_id == video_id)
    total = db.scalar(count_query) or 0
    rows = db.scalars(query.order_by(Clip.created_at.desc()).limit(limit).offset(offset))
    return list(rows), total
