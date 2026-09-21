"""Job entity: async work unit (transcribe/render/text_gen/publish/metrics_sync/ml_train)."""
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class JobType:
    TRANSCRIBE = "transcribe"
    RENDER = "render"
    TEXT_GEN = "text_gen"
    PUBLISH = "publish"
    METRICS_SYNC = "metrics_sync"
    TRAIN = "ml_train"


class JobStatus:
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class JobRefType:
    VIDEO = "video"
    CLIP = "clip"
    PUBLICATION = "publication"
    CANDIDATE = "candidate"
    SYSTEM = "system"


def _json_variant() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    job_type: Mapped[str] = mapped_column("type", sa.String(16), nullable=False)
    ref_type: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid(), nullable=True)  # None for system jobs
    status: Mapped[str] = mapped_column(sa.String(12), nullable=False, default=JobStatus.QUEUED)
    attempts: Mapped[int] = mapped_column(sa.Integer(), nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(sa.Integer(), nullable=False, default=3)
    idempotency_key: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(_json_variant(), nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(_json_variant(), nullable=True)
    error_message: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint("idempotency_key", name="uq_jobs_idempotency_key"),
        sa.CheckConstraint(
            "type IN ('transcribe', 'render', 'text_gen', 'publish', 'metrics_sync', 'ml_train')",
            name="type",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'retrying', 'cancelled')",
            name="status",
        ),
        sa.Index("ix_jobs_status_type", "status", "type"),
        sa.Index("ix_jobs_ref", "ref_type", "ref_id"),
    )
