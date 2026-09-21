"""TranscriptSegment: one whisper segment with timing and optional words."""
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    start: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    end: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    text: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    avg_confidence: Mapped[float | None] = mapped_column(sa.Float(), nullable=True)
    words: Mapped[list[Any] | None] = mapped_column(
        sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (
        sa.CheckConstraint("end > start", name="time_order"),
        sa.CheckConstraint("start >= 0", name="start_nonneg"),
        sa.Index("ix_transcript_segments_video_id_start", "video_id", "start"),
    )
