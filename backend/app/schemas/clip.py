"""Clip API schemas."""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import DateTimeUtc


class ClipCreate(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    start_sec: float = Field(ge=0)
    end_sec: float = Field(ge=0)
    # NOTE: end > start is validated in the service -> 400 invalid_range (ADR-012)


class ClipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    video_id: UUID
    title: str
    start_sec: float
    end_sec: float
    status: str
    score: float | None = None
    features: dict[str, Any] | None = None
    created_at: DateTimeUtc
    updated_at: DateTimeUtc


class ClipPage(BaseModel):
    items: list[ClipRead]
    total: int
