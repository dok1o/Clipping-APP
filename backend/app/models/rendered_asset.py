"""Rendered vertical asset (1080x1920 mp4) produced by the render pipeline."""
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RenderedAssetStatus:
    RENDERING = "rendering"
    READY = "ready"
    FAILED = "failed"


class RenderedAsset(Base):
    __tablename__ = "rendered_assets"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    clip_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("clips.id", ondelete="CASCADE"), nullable=False
    )
    storage_key: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    size_bytes: Mapped[int] = mapped_column(sa.BigInteger(), nullable=False)
    width: Mapped[int] = mapped_column(sa.Integer(), nullable=False, default=1080)
    height: Mapped[int] = mapped_column(sa.Integer(), nullable=False, default=1920)
    codec_video: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="h264")
    codec_audio: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="aac")
    pix_fmt: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="yuv420p")
    duration_sec: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(12), nullable=False, default=RenderedAssetStatus.RENDERING)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    clip: Mapped["Clip"] = relationship(back_populates="rendered_assets")  # type: ignore[name-defined] # noqa: F821

    __table_args__ = (
        sa.UniqueConstraint("storage_key", name="uq_rendered_assets_storage_key"),
        sa.CheckConstraint("status IN ('rendering', 'ready', 'failed')", name="status"),
        sa.Index("ix_rendered_assets_clip_id", "clip_id"),
    )
