"""ML training schemas (Stage 7)."""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.common import DateTimeUtc


class TrainingRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: DateTimeUtc
    status: str
    n_rows: int
    val_spearman: float | None = None
    baseline_spearman: float | None = None
    gate_passed: bool
    model_version: str | None = None
    error_message: str | None = None
    details: dict[str, Any] = {}


class TrainingRunPage(BaseModel):
    items: list[TrainingRunRead]
    total: int


class TrainAccepted(BaseModel):
    job_id: UUID
    status: str
