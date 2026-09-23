"""Job API schemas."""
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import DateTimeUtc

JobTypeL = Literal["transcribe", "render", "text_gen", "publish", "metrics_sync", "ml_train"]
JobStatusL = Literal["queued", "running", "succeeded", "failed", "retrying", "cancelled"]
JobRefTypeL = Literal["video", "clip", "publication", "candidate", "system"]


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: JobTypeL = Field(validation_alias="job_type")
    status: JobStatusL
    ref_type: JobRefTypeL
    ref_id: UUID | None = None  # None for system jobs (ml_train)
    attempts: int
    max_attempts: int
    idempotency_key: str | None = None
    payload: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error_message: str | None = None
    scheduled_at: DateTimeUtc | None = None
    started_at: DateTimeUtc | None = None
    finished_at: DateTimeUtc | None = None
    created_at: DateTimeUtc
    updated_at: DateTimeUtc


class JobPage(BaseModel):
    items: list[JobRead]
    total: int
