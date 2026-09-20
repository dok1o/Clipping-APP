"""Texts API (CONTRACTS §4.12). Stage 5: dispatch via Job (202)."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.text_gen import GeneratedTextsOut, TextGenCreate, TextGenResult
from app.services.text_gen import text_service

router = APIRouter(tags=["texts"])


@router.post("/texts/generate", response_model=TextGenResult, status_code=status.HTTP_202_ACCEPTED)
def generate_texts(payload: TextGenCreate, db: Session = Depends(get_db)) -> TextGenResult:
    """Dispatch a text_gen Job. In eager mode (dev/tests) the result is ready
    immediately; with a real worker the texts appear via GET /clips/{id}/texts."""
    from app.workers.tasks import text_gen_task

    job, texts = text_service.create_text_gen_job(
        db,
        clip_id=payload.clip_id,
        platform=payload.platform,
        tone=payload.tone,
        transcript=payload.transcript,
    )
    result = job.result or {}
    return TextGenResult(
        job_id=job.id,
        texts=GeneratedTextsOut(
            titles=result.get("titles", texts.titles if texts else []),
            description=result.get("description", texts.description if texts else ""),
            hashtags=result.get("hashtags", texts.hashtags if texts else []),
        ),
        captions_srt=result.get("captions_srt", ""),
        platform=payload.platform,
    )


@router.get("/clips/{clip_id}/texts")
def get_clip_texts(clip_id, platform: str = "youtube", db: Session = Depends(get_db)) -> dict:
    import uuid as uuid_lib

    clip_id = uuid_lib.UUID(str(clip_id))
    result = text_service.get_clip_texts(db, clip_id, platform)
    if result is None:
        return {"clip_id": str(clip_id), "platform": platform, "texts": None}
    return {
        "clip_id": str(clip_id),
        "platform": platform,
        "texts": {
            "titles": result.get("titles", []),
            "description": result.get("description", ""),
            "hashtags": result.get("hashtags", []),
            "captions_srt": result.get("captions_srt", ""),
        },
    }
