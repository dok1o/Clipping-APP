"""Candidate orchestration: transcript + scenes + loudness -> top-k candidates -> promote.

RMS loudness timeline is computed with stdlib `audioop` from the same 16k mono
WAV that whisper uses (no extra dependencies, no GPU).
"""
from __future__ import annotations

import audioop
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.infra.s3 import S3Storage
from app.models.clip import Clip, ClipStatus
from app.models.clip_candidate import ClipCandidate
from app.models.transcript import TranscriptSegment
from app.models.video import Video, VideoStatus
from app.services.ai_clipping.features import Window
from app.services.ai_clipping.heuristic_ranker import rank_candidates
from app.services.render.ffmpeg_runner import extract_audio_wav, probe_media
from app.services.transcription import scene_service

logger = get_logger(__name__)

RMS_BUCKET_SEC = 1.0


def get_video_or_404(db: Session, video_id: uuid.UUID) -> Video:
    video = db.get(Video, video_id)
    if video is None:
        raise AppError(404, "video_not_found", f"Video {video_id} not found")
    return video


def load_segments(db: Session, video_id: uuid.UUID) -> list[dict]:
    rows = db.scalars(
        select(TranscriptSegment)
        .where(TranscriptSegment.video_id == video_id)
        .order_by(TranscriptSegment.start)
    )
    return [
        {"start": r.start, "end": r.end, "text": r.text, "avg_confidence": r.avg_confidence}
        for r in rows
    ]


def rms_timeline_from_wav(wav_path: Path, bucket_sec: float = RMS_BUCKET_SEC) -> list[tuple[float, float]]:
    """Per-second RMS loudness from a 16-bit mono WAV (stdlib audioop)."""
    import wave

    timeline: list[tuple[float, float]] = []
    with wave.open(str(wav_path), "rb") as wav:
        rate = wav.getframerate()
        width = wav.getsampwidth()
        frame_size = max(1, int(rate * bucket_sec) * width)
        second = 0.0
        while True:
            chunk = wav.readframes(int(rate * bucket_sec))
            if not chunk:
                break
            try:
                rms = audioop.rms(chunk, width)
            except Exception:  # noqa: BLE001 — malformed chunk
                rms = 0
            timeline.append((second, rms))
            second += bucket_sec
            _ = frame_size
    return timeline


def generate_candidates(
    db: Session, storage: S3Storage, video_id: uuid.UUID, top_k: int = 5
) -> list[ClipCandidate]:
    """Full heuristic pipeline for a video (spec §18)."""
    settings = get_settings()
    video = get_video_or_404(db, video_id)
    if video.status != VideoStatus.READY:
        raise AppError(409, "video_not_ready", "Video is not ready")

    segments = load_segments(db, video_id)
    if not segments:
        raise AppError(
            409, "transcript_missing",
            "Transcribe the video first (POST /api/v1/videos/{id}/transcribe)",
        )

    with tempfile.TemporaryDirectory(prefix="clipper-candidates-") as tmp:
        src = Path(tmp) / "source.mp4"
        wav = Path(tmp) / "audio.wav"
        storage.download_to_file(video.storage_key, src)

        duration = video.duration_sec
        if duration is None:
            meta = probe_media(src)
            duration = (meta or {}).get("duration_sec")
            if duration:
                video.duration_sec = duration
                db.commit()
        if not duration:
            raise AppError(
                422, "video_metadata_missing",
                "Video duration is unknown (no ffprobe metadata); cannot generate windows",
            )

        boundaries = scene_service.detect_scenes(src)
        scene_fallback = False
        if len(boundaries) < 2:
            boundaries = scene_service.uniform_fallback_boundaries(duration)
            scene_fallback = True

        rms_timeline: list[tuple[float, float]] | None = None
        try:
            extract_audio_wav(src, wav)
            rms_timeline = rms_timeline_from_wav(wav)
        except Exception as exc:  # noqa: BLE001 — loudness is optional
            logger.warning("loudness timeline unavailable: %s", exc)
            rms_timeline = None

    ranked = rank_candidates(duration, segments, boundaries, rms_timeline, top_k=top_k)

    # replace previously generated candidates for this video (regeneration is idempotent-ish)
    db.query(ClipCandidate).filter(ClipCandidate.video_id == video_id).delete()
    rows = []
    for item in ranked:
        candidate = ClipCandidate(
            video_id=video_id,
            start=item.start,
            end=item.end,
            score=item.score,
            features={**item.features, "scene_boundaries": boundaries[:50],
                      "scene_fallback": scene_fallback},
            reason=item.reason,
        )
        db.add(candidate)
        rows.append(candidate)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def promote_candidate(db: Session, candidate_id: uuid.UUID, title: str | None = None) -> Clip:
    """Create a manual-editable Clip from a candidate (spec §18)."""
    candidate = db.get(ClipCandidate, candidate_id)
    if candidate is None:
        raise AppError(404, "candidate_not_found", f"Candidate {candidate_id} not found")
    video = db.get(Video, candidate.video_id)
    if video is None or video.status != VideoStatus.READY:
        raise AppError(409, "video_not_ready", "Source video is not ready")

    settings = get_settings()
    duration = candidate.end - candidate.start
    if duration < settings.clip_min_sec or duration > settings.clip_max_sec:
        raise AppError(422, "invalid_clip_state", "Candidate window violates clip limits")

    if title is None:
        seg = db.scalars(
            select(TranscriptSegment)
            .where(
                TranscriptSegment.video_id == candidate.video_id,
                TranscriptSegment.start >= candidate.start,
                TranscriptSegment.end <= candidate.end,
            )
            .order_by(TranscriptSegment.start)
            .limit(1)
        ).first()
        title = (seg.text[:60] if seg else None) or f"Клип {candidate.start:.0f}-{candidate.end:.0f}с"

    clip = Clip(
        video_id=candidate.video_id,
        title=title,
        start_sec=candidate.start,
        end_sec=candidate.end,
        status=ClipStatus.DRAFT,
        score=candidate.score,
        features=candidate.features,
    )
    db.add(clip)
    db.commit()
    db.refresh(clip)
    return clip
