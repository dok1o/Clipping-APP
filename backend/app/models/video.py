"""Video entity (uploaded source video)."""
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class VideoStatus:
    UPLOADING = "uploading"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    original_filename: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    size_bytes: Mapped[int] = mapped_column(sa.BigInteger(), nullable=False)
    mime_type: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    duration_sec: Mapped[float | None] = mapped_column(sa.Float(), nullable=True)
    width: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    error_message: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()
    )

    clips: Mapped[list["Clip"]] = relationship(  # type: ignore[name-defined] # noqa: F821
        back_populates="video"
    )

    __table_args__ = (
        sa.UniqueConstraint("storage_key", name="uq_videos_storage_key"),
        sa.CheckConstraint(
            "status IN ('uploading', 'ready', 'failed', 'deleted')", name="status"
        ),
        sa.Index("ix_videos_status", "status"),
    )
