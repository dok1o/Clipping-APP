"""Aggregated v1 API router. Sub-routers are attached as stages progress."""
from fastapi import APIRouter

api_v1_router = APIRouter(prefix="/api/v1")
