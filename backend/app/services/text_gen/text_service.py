"""Text generation orchestration: prompt building, structured validation, limits.

Platform limits (official, see docs/KNOWLEDGE.md):
  YouTube: title <= 100 chars, description <= 5000, tags total <= 500 chars.
  TikTok:  caption (title) <= 2200 chars, hashtags recommended 3-8.
Storage: texts live in Job(type=text_gen).result — the same contract survives
the Stage 5 move to async jobs (response carries job_id + texts).
"""
from __future__ import annotations

import json
import uuid
from typing import Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.models.clip import Clip
from app.models.job import Job, JobRefType, JobStatus, JobType

logger = get_logger(__name__)

Platform = Literal["youtube", "tiktok"]


class GeneratedTexts(BaseModel):
    titles: list[str] = Field(min_length=1, max_length=10)
    description: str
    hashtags: list[str] = Field(default_factory=list, max_length=20)


PLATFORM_LIMITS: dict[str, dict] = {
    "youtube": {"title_max": 100, "description_max": 5000, "tags_total_max": 500,
                "hashtags_min": 3, "hashtags_max": 8},
    "tiktok": {"title_max": 2200, "description_max": 2200, "tags_total_max": 2200,
               "hashtags_min": 3, "hashtags_max": 8},
}

PROMPT_TEMPLATE = """Ты — копирайтер коротких вертикальных видео. Сгенерируй тексты для клипа.
Платформа: {platform}
Тема клипа: {topic}
{transcript_block}{tone_block}
Требования:
- Верни СТРОГО JSON-объект: {{"titles": ["...", "...", "..."], "description": "...", "hashtags": ["#tag", ...]}}
- Ровно 3 варианта заголовка, цепляющих и по теме.
- Описание: 1-3 предложения с призывом досмотреть.
- Хэштеги: от {hashtags_min} до {hashtags_max}, без пробелов, начинаются с #.
- Только валидный JSON, без markdown и пояснений.
"""


def get_provider():
    settings = get_settings()
    if settings.llm_backend == "fake":
        from app.services.text_gen.fake_provider import FakeTextGenProvider

        return FakeTextGenProvider()
    if settings.llm_backend == "ollama":
        from app.services.text_gen.local_provider import LocalTextGenProvider

        return LocalTextGenProvider()
    # llamacpp / transformers are wired through local_provider (not_implemented error)
    from app.services.text_gen.local_provider import LocalTextGenProvider

    return LocalTextGenProvider()


def build_prompt(clip: Clip, platform: str, tone: str | None, transcript: str | None) -> str:
    limits = PLATFORM_LIMITS[platform]
    transcript_block = f"Фрагмент транскрипта:\n{transcript[:1500]}\n" if transcript else ""
    tone_block = f"Тон: {tone}\n" if tone else ""
    return PROMPT_TEMPLATE.format(
        platform=platform,
        topic=clip.title,
        transcript_block=transcript_block,
        tone_block=tone_block,
        hashtags_min=limits["hashtags_min"],
        hashtags_max=limits["hashtags_max"],
    )


def parse_and_validate(raw: str) -> GeneratedTexts:
    """Strict JSON -> Pydantic; one retry is handled by the caller (spec §16)."""
    try:
        return GeneratedTexts.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError):
        # tolerate markdown fences some models add
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return GeneratedTexts.model_validate(json.loads(cleaned))


def apply_platform_limits(texts: GeneratedTexts, platform: str) -> GeneratedTexts:
    limits = PLATFORM_LIMITS[platform]
    titles = [t[: limits["title_max"]].strip() for t in texts.titles]
    description = texts.description[: limits["description_max"]].strip()
    hashtags = [h if h.startswith("#") else f"#{h}" for h in texts.hashtags]
    hashtags = hashtags[: limits["hashtags_max"]]
    total_tag_len = sum(len(h) + 1 for h in hashtags)
    while hashtags and total_tag_len > limits["tags_total_max"]:
        removed = hashtags.pop()
        total_tag_len -= len(removed) + 1
    return GeneratedTexts(titles=titles, description=description, hashtags=hashtags)


def create_text_gen_job(
    db: Session,
    *,
    clip_id: uuid.UUID,
    platform: str,
    tone: str | None = None,
    transcript: str | None = None,
) -> tuple[Job, GeneratedTexts | None]:
    """Validate + create a queued Job and run it (eager) or leave queued (worker).

    Returns (job, texts_or_none): texts present when the job already executed
    (eager mode); otherwise fetched via GET /clips/{id}/texts."""
    if platform not in PLATFORM_LIMITS:
        raise AppError(422, "validation_error", "platform must be youtube or tiktok")
    clip = db.get(Clip, clip_id)
    if clip is None:
        raise AppError(404, "clip_not_found", f"Clip {clip_id} not found")

    from app.core.config import get_settings as _gs

    job = Job(
        job_type=JobType.TEXT_GEN,
        ref_type=JobRefType.CLIP,
        ref_id=clip_id,
        status=JobStatus.QUEUED,
        payload={"clip_id": str(clip_id), "platform": platform, "tone": tone},
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    if _gs().celery_eager_by_default:
        return execute_text_gen_job(
            db, job.id, clip_id=clip_id, platform=platform, tone=tone, transcript=transcript
        ), None
    from app.workers.tasks import text_gen_task

    text_gen_task.delay(job.id, str(clip_id), platform, tone, transcript)
    return job, None


def execute_text_gen_job(
    db: Session,
    job_id: uuid.UUID,
    *,
    clip_id: uuid.UUID,
    platform: str,
    tone: str | None = None,
    transcript: str | None = None,
) -> Job:
    return _generate_and_record(
        db, job_id, clip_id=clip_id, platform=platform, tone=tone, transcript=transcript
    )


def _generate_and_record(
    db: Session,
    job_id: uuid.UUID,
    *,
    clip_id: uuid.UUID,
    platform: str,
    tone: str | None = None,
    transcript: str | None = None,
) -> Job:
    from app.services.text_gen.base import TextGenError

    clip = db.get(Clip, clip_id)
    if clip is None:
        raise AppError(404, "clip_not_found", f"Clip {clip_id} not found")

    settings = get_settings()
    prompt = build_prompt(clip, platform, tone, transcript)
    provider = get_provider()

    job = db.get(Job, job_id)
    if job is None:
        raise AppError(404, "job_not_found", f"Job {job_id} not found")
    job.status = JobStatus.RUNNING
    db.commit()

    raw = None
    error: str | None = None
    for attempt in (1, 2):  # one retry on invalid JSON (spec §16)
        try:
            raw = provider.generate(
                prompt, platform,
                max_tokens=settings.llm_max_tokens,
                temperature=settings.llm_temperature,
                timeout_sec=settings.llm_timeout_sec,
            )
            texts = parse_and_validate(raw)
            break
        except TextGenError as exc:
            error = f"{exc.code}: {exc.message}"
            job.error_message = error
            job.status = JobStatus.FAILED
            job.attempts = attempt
            db.commit()
            db.refresh(job)
            raise AppError(502, "text_gen_error", exc.message) from exc
        except (json.JSONDecodeError, ValidationError) as exc:
            if attempt == 2:
                job.status = JobStatus.FAILED
                job.error_message = f"invalid_json: {exc}"[:500]
                job.attempts = attempt
                db.commit()
                db.refresh(job)
                raise AppError(502, "text_gen_error", "Model returned invalid JSON after retry") from exc
            logger.warning("invalid JSON from LLM (attempt 1), retrying once")
    else:  # pragma: no cover
        raise AppError(502, "text_gen_error", "generation failed")

    job.attempts = 1
    texts = apply_platform_limits(texts, platform)
    payload = {
        "platform": platform,
        "titles": texts.titles,
        "description": texts.description,
        "hashtags": texts.hashtags,
        "captions_srt": build_captions_srt(transcript),
    }
    job.result = payload
    job.status = JobStatus.SUCCEEDED
    db.commit()
    db.refresh(job)
    return job


def build_captions_srt(transcript: str | None) -> str:
    """Stage 2: empty without a transcript (Stage 3 wires real segments)."""
    return "" if not transcript else transcript  # placeholder; replaced in Stage 3


def get_clip_texts(db: Session, clip_id: uuid.UUID, platform: str) -> dict | None:
    """Latest succeeded text_gen job for (clip, platform) — CONTRACTS §4.12."""
    clip = db.get(Clip, clip_id)
    if clip is None:
        raise AppError(404, "clip_not_found", f"Clip {clip_id} not found")
    jobs = db.scalars(
        select(Job)
        .where(
            Job.ref_id == clip_id,
            Job.job_type == JobType.TEXT_GEN,
            Job.status == JobStatus.SUCCEEDED,
        )
        .order_by(Job.created_at.desc())
    )
    for job in jobs:
        result = job.result or {}
        if result.get("platform") == platform:
            return result
    return None
