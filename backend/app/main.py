from fastapi import FastAPI

from app.ingestion.router import clip_router
from app.ingestion.router import router as ingestion_router
from app.video_effects.router import router as video_effects_router


app = FastAPI(title="AI Clipper")
app.include_router(ingestion_router)
app.include_router(clip_router)
app.include_router(video_effects_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
