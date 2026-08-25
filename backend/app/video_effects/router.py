from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.infra.database import get_session
from app.infra.models import Clip, RenderedAsset, Video
from app.infra.storage import ObjectStorage, get_object_storage
from app.video_effects.renderer import (
    FfmpegRenderError,
    OUTPUT_FORMAT,
    TARGET_HEIGHT,
    TARGET_WIDTH,
    render_vertical_clip,
)
from app.video_effects.schemas import RenderedAssetResponse


router = APIRouter(prefix="/clips", tags=["video-effects"])

CLIP_STATUS_RENDERING = "rendering"
CLIP_STATUS_RENDERED = "rendered"
CLIP_STATUS_FAILED = "failed"


@router.post("/{clip_id}/render", response_model=RenderedAssetResponse, status_code=status.HTTP_201_CREATED)
def render_clip(
    clip_id: UUID,
    session: Session = Depends(get_session),
    storage: ObjectStorage = Depends(get_object_storage),
) -> RenderedAsset:
    clip = _get_clip_or_404(clip_id, session)
    video = _get_video_or_404(clip.video_id, session)
    source_key = video.storage_key or video.source_path
    if not source_key:
        _mark_clip_failed(clip, session)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Source video object is not configured")
    if not storage.exists(source_key):
        _mark_clip_failed(clip, session)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source video object not found")

    _set_clip_status(clip, CLIP_STATUS_RENDERING, session)
    asset_id = uuid4()
    output_storage_key = f"rendered_assets/{clip.id}/{asset_id}.{OUTPUT_FORMAT}"
    duration = float(clip.end - clip.start)

    with TemporaryDirectory() as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        input_path = temp_dir / "input"
        output_path = temp_dir / f"output.{OUTPUT_FORMAT}"

        try:
            storage.download_file(source_key, input_path)
            render_vertical_clip(input_path, output_path, start=float(clip.start), duration=duration)
            storage.upload_file(output_path, output_storage_key)
        except FfmpegRenderError:
            _mark_clip_failed(clip, session)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="ffmpeg render failed")
        except Exception:
            _mark_clip_failed(clip, session)
            raise

    rendered_asset = RenderedAsset(
        id=asset_id,
        clip_id=clip.id,
        storage_key=output_storage_key,
        format=OUTPUT_FORMAT,
        width=TARGET_WIDTH,
        height=TARGET_HEIGHT,
        duration=Decimal(str(duration)),
        created_at=datetime.now(UTC),
    )

    try:
        session.add(rendered_asset)
        clip.status = CLIP_STATUS_RENDERED
        session.commit()
        session.refresh(rendered_asset)
    except Exception:
        session.rollback()
        raise

    return rendered_asset


@router.get("/{clip_id}/rendered-assets", response_model=list[RenderedAssetResponse])
def list_rendered_assets(clip_id: UUID, session: Session = Depends(get_session)) -> list[RenderedAsset]:
    clip = _get_clip_or_404(clip_id, session)
    return list(clip.rendered_assets)


def _get_clip_or_404(clip_id: UUID, session: Session) -> Clip:
    clip = session.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")
    return clip


def _get_video_or_404(video_id: UUID, session: Session) -> Video:
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    return video


def _set_clip_status(clip: Clip, clip_status: str, session: Session) -> None:
    clip.status = clip_status
    session.commit()


def _mark_clip_failed(clip: Clip, session: Session) -> None:
    _set_clip_status(clip, CLIP_STATUS_FAILED, session)
