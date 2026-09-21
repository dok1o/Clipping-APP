"""Clip entity (a cut-out moment of a video, manual or promoted from a candidate)."""
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ClipStatus:
    DRAFT = "draft"
    RENDER_QUEUED = "render_queued"
    RENDERING = "rendering"
    RENDERED = "rendered"
    RENDER_FAILED = "render_failed"


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("videos.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(sa.String(140), nullable=False)
    start_sec: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    end_sec: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False, default=ClipStatus.DRAFT)
    score: Mapped[float | None] = mapped_column(sa.Float(), nullable=True)
    features: Mapped[dict[str, Any] | None] = mapped_column(
        sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()
    )

    video: Mapped["Video"] = relationship(back_populates="clips")  # type: ignore[name-defined] # noqa: F821
    rendered_assets: Mapped[list["RenderedAsset"]] = relationship(  # type: ignore[name-defined] # noqa: F821
        back_populates="clip"
    )
    publications: Mapped[list["Publication"]] = relationship(  # type: ignore[name-defined] # noqa: F821
        back_populates="clip"
    )

    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('draft', 'render_queued', 'rendering', 'rendered', 'render_failed')",
            name="status",
        ),
        sa.CheckConstraint("end_sec > start_sec", name="time_order"),
        sa.CheckConstraint("start_sec >= 0", name="start_nonneg"),
        sa.Index("ix_clips_video_id_status", "video_id", "status"),
    )
