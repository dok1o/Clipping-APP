"""Publication: a clip being posted to a platform (manual or scheduled)."""
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PublicationStatus:
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    UPLOADING = "uploading"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Publication(Base):
    __tablename__ = "publications"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    clip_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("clips.id", ondelete="RESTRICT"), nullable=False
    )
    rendered_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("rendered_assets.id", ondelete="SET NULL"), nullable=True
    )
    platform_account_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("platform_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    platform: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    external_post_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False, default=PublicationStatus.DRAFT)
    scheduled_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    attempt_count: Mapped[int] = mapped_column(sa.Integer(), nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()
    )

    clip: Mapped["Clip"] = relationship(back_populates="publications")  # type: ignore[name-defined] # noqa: F821

    __table_args__ = (
        sa.UniqueConstraint("idempotency_key", name="uq_publications_idempotency_key"),
        sa.CheckConstraint("platform IN ('youtube', 'tiktok')", name="platform"),
        sa.CheckConstraint(
            "status IN ('draft', 'scheduled', 'uploading', 'published', 'failed', 'cancelled')",
            name="status",
        ),
        sa.Index("ix_publications_clip_platform_status", "clip_id", "platform", "status"),
        # at most ONE active publication per (clip, platform)
        sa.Index(
            "uq_publications_active", "clip_id", "platform", unique=True,
            postgresql_where=sa.text("status NOT IN ('cancelled', 'failed')"),
            sqlite_where=sa.text("status NOT IN ('cancelled', 'failed')"),
        ),
    )
