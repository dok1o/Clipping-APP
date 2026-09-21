"""Metric entity (Stage 6, CONTRACTS §2.7): raw + normalized platform stats."""
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Metric(Base):
    __tablename__ = "metrics"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    publication_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("publications.id", ondelete="CASCADE"), nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    views: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    likes: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    comments: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    shares: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    raw: Mapped[dict[str, Any]] = mapped_column(
        sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
    )

    __table_args__ = (
        sa.Index("ix_metrics_publication_captured", "publication_id", "captured_at"),
    )
