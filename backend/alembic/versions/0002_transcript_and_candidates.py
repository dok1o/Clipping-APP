"""transcript_segments + clip_candidates (Stage 3)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOW = sa.text("CURRENT_TIMESTAMP")


def _json() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("start", sa.Float(), nullable=False),
        sa.Column("end", sa.Float(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("avg_confidence", sa.Float(), nullable=True),
        sa.Column("words", _json(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], name="fk_transcript_segments_video_id_videos", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_transcript_segments"),
        sa.CheckConstraint("end > start", name="time_order"),
        sa.CheckConstraint("start >= 0", name="start_nonneg"),
    )
    op.create_index("ix_transcript_segments_video_id_start", "transcript_segments", ["video_id", "start"])

    op.create_table(
        "clip_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("start", sa.Float(), nullable=False),
        sa.Column("end", sa.Float(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("features", _json(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], name="fk_clip_candidates_video_id_videos", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_clip_candidates"),
        sa.CheckConstraint("end > start", name="time_order"),
        sa.CheckConstraint("start >= 0", name="start_nonneg"),
    )
    op.create_index("ix_clip_candidates_video_id_score", "clip_candidates", ["video_id", "score"])


def downgrade() -> None:
    op.drop_index("ix_clip_candidates_video_id_score", table_name="clip_candidates")
    op.drop_table("clip_candidates")
    op.drop_index("ix_transcript_segments_video_id_start", table_name="transcript_segments")
    op.drop_table("transcript_segments")
