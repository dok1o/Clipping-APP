"""Aggregated v1 API router. Sub-routers are attached as stages progress."""
from fastapi import APIRouter

from app.api.v1 import jobs

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(jobs.router, tags=["jobs"])
