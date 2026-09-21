"""PlatformAccount: a connected creator account (TikTok / YouTube).

Credentials are Fernet-encrypted (app/core/security.py); NEVER stored in plain
text and masked in every API response (CONTRACTS §2).
"""
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlatformAccount(Base):
    __tablename__ = "platform_accounts"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    platform: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    external_account_id: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    credentials_encrypted: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    scopes: Mapped[list[Any]] = mapped_column(
        sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False, default=list
    )
    expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()
    )

    __table_args__ = (
        sa.CheckConstraint("platform IN ('youtube', 'tiktok')", name="platform"),
        sa.UniqueConstraint(
            "platform", "external_account_id",
            name="uq_platform_accounts_platform_external_account_id",
        ),
        sa.Index("ix_platform_accounts_platform_is_active", "platform", "is_active"),
    )
