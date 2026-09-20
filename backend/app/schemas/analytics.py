"""Analytics API schemas."""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.common import DateTimeUtc


class MetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    publication_id: UUID
    captured_at: DateTimeUtc
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    raw: dict[str, Any] | None = None


class MetricPage(BaseModel):
    items: list[MetricRead]
    total: int


class MetricsSyncAccepted(BaseModel):
    job_id: UUID
    publication_id: UUID
    status: str
