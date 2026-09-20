"""Transcription API schemas."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.common import DateTimeUtc


class TranscriptSegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    video_id: UUID
    start: float
    end: float
    text: str
    avg_confidence: float | None = None
    created_at: DateTimeUtc


class TranscriptPage(BaseModel):
    items: list[TranscriptSegmentRead]
    total: int


class TranscribeAccepted(BaseModel):
    job_id: UUID
    video_id: UUID
    status: str
