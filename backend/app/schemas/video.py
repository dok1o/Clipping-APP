"""Video API schemas."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.common import DateTimeUtc


class VideoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_filename: str
    storage_key: str
    size_bytes: int
    mime_type: str
    duration_sec: float | None = None
    width: int | None = None
    height: int | None = None
    status: str
    error_message: str | None = None
    created_at: DateTimeUtc
    updated_at: DateTimeUtc


class VideoPage(BaseModel):
    items: list[VideoRead]
    total: int
