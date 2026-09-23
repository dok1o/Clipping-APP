"""Aggregated v1 API router. Sub-routers are attached as stages progress."""
from fastapi import APIRouter

from app.api.v1 import (
    analytics,
    candidates,
    clips,
    jobs,
    ml,
    overview,
    publications,
    renders,
    texts,
    transcripts,
    videos,
)

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(jobs.router, tags=["jobs"])
api_v1_router.include_router(videos.router)
api_v1_router.include_router(clips.router)
api_v1_router.include_router(renders.router)
api_v1_router.include_router(publications.router)
api_v1_router.include_router(texts.router)
api_v1_router.include_router(transcripts.router)
api_v1_router.include_router(candidates.router)
api_v1_router.include_router(analytics.router)
api_v1_router.include_router(ml.router)
api_v1_router.include_router(overview.router)
