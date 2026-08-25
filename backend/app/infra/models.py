from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.database import Base


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    clips: Mapped[list[Clip]] = relationship(back_populates="video")


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    video_id: Mapped[UUID] = mapped_column(ForeignKey("videos.id"), nullable=False, index=True)
    start: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    end: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    video: Mapped[Video] = relationship(back_populates="clips")
    rendered_assets: Mapped[list[RenderedAsset]] = relationship(back_populates="clip")
    publications: Mapped[list[Publication]] = relationship(back_populates="clip")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), nullable=False, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class RenderedAsset(Base):
    __tablename__ = "rendered_assets"

    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    clip_id: Mapped[UUID] = mapped_column(ForeignKey("clips.id"), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    format: Mapped[str] = mapped_column(String(32), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    duration: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    clip: Mapped[Clip] = relationship(back_populates="rendered_assets")


class PlatformAccount(Base):
    __tablename__ = "platform_accounts"
    __table_args__ = (
        Index("ix_platform_accounts_platform_external_account_id", "platform", "external_account_id"),
    )

    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    external_account_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_credentials: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    publications: Mapped[list[Publication]] = relationship(back_populates="account")


class Publication(Base):
    __tablename__ = "publications"

    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    clip_id: Mapped[UUID] = mapped_column(ForeignKey("clips.id"), nullable=False, index=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("platform_accounts.id"), nullable=False, index=True)
    external_post_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    clip: Mapped[Clip] = relationship(back_populates="publications")
    account: Mapped[PlatformAccount] = relationship(back_populates="publications")
