"""metrics table (Stage 6)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOW = sa.text("CURRENT_TIMESTAMP")


def _json() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "metrics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("publication_id", sa.Uuid(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("views", sa.BigInteger(), nullable=True),
        sa.Column("likes", sa.BigInteger(), nullable=True),
        sa.Column("comments", sa.BigInteger(), nullable=True),
        sa.Column("shares", sa.BigInteger(), nullable=True),
        sa.Column("raw", _json(), nullable=False),
        sa.ForeignKeyConstraint(
            ["publication_id"], ["publications.id"],
            name="fk_metrics_publication_id_publications", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_metrics"),
    )
    op.create_index("ix_metrics_publication_captured", "metrics", ["publication_id", "captured_at"])


def downgrade() -> None:
    op.drop_index("ix_metrics_publication_captured", table_name="metrics")
    op.drop_table("metrics")
