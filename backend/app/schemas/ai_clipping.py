"""AI clipping candidate schemas."""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import DateTimeUtc


class CandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    video_id: UUID
    start: float
    end: float
    score: float
    features: dict[str, Any]
    reason: str
    created_at: DateTimeUtc


class CandidatePage(BaseModel):
    items: list[CandidateRead]
    total: int
    ranked_by: str = "heuristic"  # "heuristic" | "ml" (Stage 7)


class PromoteRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=140)
