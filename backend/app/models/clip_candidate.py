"""ClipCandidate: an AI-suggested moment (heuristic or ML ranked)."""
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ClipCandidate(Base):
    __tablename__ = "clip_candidates"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    start: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    end: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    score: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    features: Mapped[dict[str, Any]] = mapped_column(
        sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False, default=dict
    )
    reason: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (
        sa.CheckConstraint("end > start", name="time_order"),
        sa.CheckConstraint("start >= 0", name="start_nonneg"),
        sa.Index("ix_clip_candidates_video_id_score", "video_id", "score"),
    )
