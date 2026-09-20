"""Render orchestration: Clip/Job lifecycle + S3 artifacts (CONTRACTS §4.7–§4.9, §5).

Status flow: clip draft|render_failed -> render_queued (Job created)
-> rendering (ffmpeg started) -> rendered (asset ready) | render_failed.
"""
from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.infra.s3 import S3Storage
from app.models.clip import Clip, ClipStatus
from app.models.job import Job, JobRefType, JobStatus, JobType
from app.models.rendered_asset import RenderedAsset, RenderedAssetStatus
from app.models.video import Video, VideoStatus
from app.services.render.ffmpeg_runner import RenderError, render_vertical

logger = get_logger(__name__)


def get_clip_or_404(db: Session, clip_id: uuid.UUID) -> Clip:
    clip = db.get(Clip, clip_id)
    if clip is None:
        from app.core.errors import AppError

        raise AppError(404, "clip_not_found", f"Clip {clip_id} not found")
    return clip


def latest_ready_asset(db: Session, clip_id: uuid.UUID) -> RenderedAsset | None:
    return db.scalars(
        select(RenderedAsset)
        .where(RenderedAsset.clip_id == clip_id, RenderedAsset.status == RenderedAssetStatus.READY)
        .order_by(RenderedAsset.created_at.desc())
        .limit(1)
    ).first()


def queue_render(db: Session, clip_id: uuid.UUID) -> tuple[Job, str]:
    """Idempotency contract (CONTRACTS §4.7):

    - rendered + asset ready -> return the existing succeeded job (status 'rendered')
    - render_queued|rendering -> 409 already_rendering
    - rendered but asset missing -> 422 invalid_clip_state
    - draft|render_failed -> create a new Job (key render:{clip_id}:{n})
    """
    from app.core.errors import AppError

    clip = get_clip_or_404(db, clip_id)

    video = db.get(Video, clip.video_id)
    if video is None or video.status != VideoStatus.READY:
        raise AppError(422, "invalid_clip_state", "Clip video is not ready")

    if clip.status in (ClipStatus.RENDER_QUEUED, ClipStatus.RENDERING):
        raise AppError(409, "already_rendering", f"Clip {clip_id} render is already in progress")

    if clip.status == ClipStatus.RENDERED:
        asset = latest_ready_asset(db, clip_id)
        if asset is not None:
            job = _latest_job(db, clip_id, JobType.RENDER, JobStatus.SUCCEEDED)
            if job is not None:
                return job, "rendered"
            # asset exists without a job record — synthesize a stable answer
            job = Job(
                job_type=JobType.RENDER,
                ref_type=JobRefType.CLIP,
                ref_id=clip_id,
                status=JobStatus.SUCCEEDED,
                result={"asset_id": str(asset.id)},
            )
            db.add(job)
            db.commit()
            return job, "rendered"
        raise AppError(422, "invalid_clip_state", "Clip marked rendered but no ready asset found")

    # draft | render_failed -> queue a fresh render
    n = _count_prior_renders(db, clip_id)
    job = Job(
        job_type=JobType.RENDER,
        ref_type=JobRefType.CLIP,
        ref_id=clip_id,
        status=JobStatus.QUEUED,
        idempotency_key=f"render:{clip_id}:{n}",
        payload={"clip_id": str(clip_id), "start_sec": clip.start_sec, "end_sec": clip.end_sec},
    )
    db.add(job)
    clip.status = ClipStatus.RENDER_QUEUED
    db.commit()
    db.refresh(job)
    return job, "render_queued"


def _latest_job(db: Session, ref_id: uuid.UUID, job_type: str, status: str) -> Job | None:
    return db.scalars(
        select(Job)
        .where(Job.ref_id == ref_id, Job.job_type == job_type, Job.status == status)
        .order_by(Job.created_at.desc())
        .limit(1)
    ).first()


def _count_prior_renders(db: Session, clip_id: uuid.UUID) -> int:
    from sqlalchemy import func

    return (
        db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.ref_id == clip_id, Job.job_type == JobType.RENDER)
        )
        or 0
    )


def execute_render_job(
    db: Session, storage: S3Storage, job_id: uuid.UUID
) -> Job:
    """Run the render for a queued Job. Never raises for render-level failures:
    the Job/Clip transition to failed states with a controlled error code."""
    job = db.get(Job, job_id)
    if job is None:
        raise ValueError(f"Job {job_id} not found")
    clip = db.get(Clip, job.ref_id)

    job.status = JobStatus.RUNNING
    job.started_at = datetime.now(timezone.utc)
    job.attempts += 1
    if clip is not None:
        clip.status = ClipStatus.RENDERING
    db.commit()

    try:
        if clip is None:
            raise RenderError("render_failed", "clip not found")
        video = db.get(Video, clip.video_id)
        if video is None:
            raise RenderError("render_failed", "video not found")

        asset = RenderedAsset(
            clip_id=clip.id,
            storage_key="pending",  # replaced after id is known
            size_bytes=0,
            duration_sec=clip.end_sec - clip.start_sec,
            status=RenderedAssetStatus.RENDERING,
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)
        asset.storage_key = f"renders/{clip.id}/{asset.id}.mp4"
        db.commit()

        with tempfile.TemporaryDirectory(prefix="clipper-render-") as tmp_dir:
            tmp = Path(tmp_dir)
            src = tmp / f"source{Path(video.storage_key).suffix or '.mp4'}"
            dst = tmp / "render.mp4"
            storage.download_to_file(video.storage_key, src)
            render_vertical(
                src,
                dst,
                start_sec=clip.start_sec,
                duration_sec=clip.end_sec - clip.start_sec,
            )
            storage.upload_file(dst, asset.storage_key, content_type="video/mp4")
            asset.size_bytes = dst.stat().st_size

        asset.status = RenderedAssetStatus.READY
        clip.status = ClipStatus.RENDERED
        job.status = JobStatus.SUCCEEDED
        job.finished_at = datetime.now(timezone.utc)
        job.result = {"asset_id": str(asset.id)}
        db.commit()
    except RenderError as exc:
        job.status = JobStatus.FAILED
        job.finished_at = datetime.now(timezone.utc)
        job.error_message = f"{exc.code}: {exc.message}"
        if exc.stderr_tail:
            job.error_message += f" | stderr tail: {exc.stderr_tail}"
        if clip is not None:
            clip.status = ClipStatus.RENDER_FAILED
        db.commit()
    except Exception as exc:  # noqa: BLE001 — controlled storage/infra error
        logger.exception("render job crashed")
        job.status = JobStatus.FAILED
        job.finished_at = datetime.now(timezone.utc)
        job.error_message = f"internal_error: {exc}"[:2000]
        if clip is not None:
            clip.status = ClipStatus.RENDER_FAILED
        db.commit()

    db.refresh(job)
    return job
