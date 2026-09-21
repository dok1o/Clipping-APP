"""TrainingRun (Stage 7): one ML rerank training attempt + eval-gate decision."""
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TrainingRun(Base):
    __tablename__ = "training_runs"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False)  # succeeded|rejected|failed
    n_rows: Mapped[int] = mapped_column(sa.Integer(), nullable=False, default=0)
    val_spearman: Mapped[float | None] = mapped_column(sa.Float(), nullable=True)
    baseline_spearman: Mapped[float | None] = mapped_column(sa.Float(), nullable=True)
    gate_passed: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=False)
    model_version: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    model_path: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(sa.String(2000), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(
        sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False, default=dict
    )

    __table_args__ = (
        sa.Index("ix_training_runs_created", "created_at"),
    )
