"""faster-whisper transcription with device fallback (master spec §17).

faster-whisper is an OPTIONAL dependency (extras [whisper]); it is imported
lazily so the main test suite and API work without it (mocked in tests, real
check via scripts/verify_whisper.py on a GPU/CPU machine).

GPU (8GB): device=cuda + int8_float16 by default; on CUDA runtime failure -> CPU + int8.
`device_used` is recorded in the Job result (spec §17).
"""
from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.job import Job, JobRefType, JobStatus, JobType
from app.models.transcript import TranscriptSegment
from app.models.video import Video, VideoStatus
from app.services.render.ffmpeg_runner import RenderError, extract_audio_wav

logger = get_logger(__name__)

CUDA_FAILURE_MARKERS = (
    "cuda",
    "cublas",
    "cudnn",
    "nvidia",
    "out of memory",
    "insufficient driver",
)


class TranscribeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _cuda_available() -> bool:
    try:
        import ctranslate2  # type: ignore

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:  # noqa: BLE001
        return False


def resolve_device(setting: str) -> str:
    """auto -> cuda when available, else cpu."""
    if setting == "auto":
        return "cuda" if _cuda_available() else "cpu"
    return setting


def resolve_compute_type(device: str, setting: str) -> str:
    """CPU always falls back to int8 (spec §17)."""
    if device == "cpu" and setting == "int8_float16":
        return "int8"
    return setting


def _is_cuda_failure(message: str) -> bool:
    normalized = message.lower()
    return any(marker in normalized for marker in CUDA_FAILURE_MARKERS)


def transcribe_audio(
    wav_path: str | Path, *, model_name: str | None = None, device: str | None = None,
) -> tuple[list[dict], dict]:
    """Run faster-whisper; returns (segments, info).

    segments: [{"start": float, "end": float, "text": str, "avg_confidence": float|None}]
    info: {"device_used": str, "compute_type": str, "model": str}
    Raises TranscribeError (whisper_unavailable / cuda_oom / transcription_failed).
    """
    settings = get_settings()
    model_name = model_name or settings.whisper_model
    wanted_device = resolve_device(device or settings.whisper_device)

    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as exc:
        raise TranscribeError(
            "whisper_unavailable",
            "faster-whisper is not installed (pip install -e '.[whisper]')",
        ) from exc

    compute = resolve_compute_type(wanted_device, settings.whisper_compute_type)
    try:
        model = WhisperModel(model_name, device=wanted_device, compute_type=compute)
        segments_iter, audio_info = model.transcribe(
            str(wav_path), beam_size=settings.whisper_beam_size
        )
        segments = []
        for seg in segments_iter:
            avg_confidence = None
            probs = getattr(seg, "avg_logprob", None)
            if probs is not None:
                avg_confidence = round(float(2.718281828 ** probs), 3)  # logprob -> ~probability
            segments.append({
                "start": float(seg.start),
                "end": float(seg.end),
                "text": seg.text.strip(),
                "avg_confidence": avg_confidence,
            })
        info = {
            "device_used": wanted_device,
            "compute_type": compute,
            "model": model_name,
            "duration": float(getattr(audio_info, "duration", 0.0)),
            "language": getattr(audio_info, "language", None),
        }
        return segments, info
    except TranscribeError:
        raise
    except Exception as exc:  # noqa: BLE001 — controlled failure
        message = str(exc)
        if wanted_device == "cuda" and _is_cuda_failure(message):
            logger.warning("CUDA transcription failed — falling back to CPU/int8: %s", message)
            try:
                model = WhisperModel(model_name, device="cpu", compute_type="int8")
                segments_iter, audio_info = model.transcribe(
                    str(wav_path), beam_size=settings.whisper_beam_size
                )
                segments = [
                    {"start": float(s.start), "end": float(s.end), "text": s.text.strip(),
                     "avg_confidence": None}
                    for s in segments_iter
                ]
                return segments, {"device_used": "cpu", "compute_type": "int8",
                                  "model": model_name,
                                  "duration": float(getattr(audio_info, "duration", 0.0)),
                                  "language": getattr(audio_info, "language", None)}
            except Exception as cpu_exc:  # noqa: BLE001
                raise TranscribeError("transcription_failed", f"CPU fallback failed: {cpu_exc}") from cpu_exc
        raise TranscribeError("transcription_failed", message[:500]) from exc


def queue_transcription(db: Session, video_id: uuid.UUID) -> Job:
    from app.core.errors import AppError
    from sqlalchemy import select

    video = db.get(Video, video_id)
    if video is None:
        raise AppError(404, "video_not_found", f"Video {video_id} not found")
    if video.status != VideoStatus.READY:
        raise AppError(409, "video_not_ready", "Video is not ready")

    existing = db.scalar(
        select(Job).where(Job.idempotency_key == f"transcribe:{video_id}")
    )
    if existing is not None:
        return existing  # idempotent: same key -> same job (cached result on re-run)

    job = Job(
        job_type=JobType.TRANSCRIBE,
        ref_type=JobRefType.VIDEO,
        ref_id=video_id,
        status=JobStatus.QUEUED,
        idempotency_key=f"transcribe:{video_id}",
        payload={"video_id": str(video_id)},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def execute_transcription_job(
    db: Session, storage, job_id: uuid.UUID
) -> Job:
    """Download source -> extract wav -> transcribe -> save segments. Job-level failures
    never crash the worker: job failed + error_message."""
    import tempfile

    from app.core.errors import AppError

    job = db.get(Job, job_id)
    if job is None:
        raise ValueError(f"Job {job_id} not found")
    job.status = JobStatus.RUNNING
    db.commit()

    try:
        video = db.get(Video, job.ref_id)
        if video is None:
            raise TranscribeError("video_not_found", "video not found")

        existing = db.query(TranscriptSegment).filter(
            TranscriptSegment.video_id == video.id
        ).count()
        if existing:
            job.result = {"segment_count": existing, "device_used": None, "cached": True}
            job.status = JobStatus.SUCCEEDED
            db.commit()
            db.refresh(job)
            return job

        with tempfile.TemporaryDirectory(prefix="clipper-transcribe-") as tmp:
            src = Path(tmp) / "source.mp4"
            wav = Path(tmp) / "audio.wav"
            storage.download_to_file(video.storage_key, src)
            try:
                extract_audio_wav(src, wav)
            except RenderError as exc:
                raise TranscribeError(exc.code, exc.message) from exc
            segments, info = transcribe_audio(wav)

        for seg in segments:
            if not seg["text"]:
                continue
            db.add(TranscriptSegment(
                video_id=video.id,
                start=seg["start"],
                end=seg["end"],
                text=seg["text"],
                avg_confidence=seg.get("avg_confidence"),
            ))
        job.result = {
            "segment_count": len(segments),
            "device_used": info.get("device_used"),
            "compute_type": info.get("compute_type"),
            "model": info.get("model"),
            "language": info.get("language"),
        }
        job.status = JobStatus.SUCCEEDED
        db.commit()
    except TranscribeError as exc:
        job.status = JobStatus.FAILED
        job.error_message = f"{exc.code}: {exc.message}"[:2000]
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("transcription job crashed")
        job.status = JobStatus.FAILED
        job.error_message = f"internal_error: {exc}"[:2000]
        db.commit()

    db.refresh(job)
    return job
