"""Texts API (CONTRACTS §4.12)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.text_gen import GeneratedTextsOut, TextGenCreate, TextGenResult
from app.services.text_gen import text_service

router = APIRouter(tags=["texts"])


@router.post("/texts/generate", response_model=TextGenResult)
def generate_texts(payload: TextGenCreate, db: Session = Depends(get_db)) -> TextGenResult:
    job, texts = text_service.generate_for_clip(
        db,
        clip_id=payload.clip_id,
        platform=payload.platform,
        tone=payload.tone,
        transcript=payload.transcript,
    )
    result = job.result or {}
    return TextGenResult(
        job_id=None,  # synchronous in Stage 2; Stage 5 keeps the same response shape
        texts=GeneratedTextsOut(
            titles=result.get("titles", texts.titles),
            description=result.get("description", texts.description),
            hashtags=result.get("hashtags", texts.hashtags),
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
