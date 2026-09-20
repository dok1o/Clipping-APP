"""initial core domain tables (videos, clips, jobs, rendered_assets, platform_accounts, publications)

Revision ID: 0001
Revises:
Create Date: 2026-09-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOW = sa.text("CURRENT_TIMESTAMP")


def _json() -> sa.types.TypeEngine:
    """JSONB on PostgreSQL, JSON on other dialects (SQLite in tests) — mirrors models."""
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "videos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_videos"),
        sa.UniqueConstraint("storage_key", name="uq_videos_storage_key"),
        sa.CheckConstraint("status IN ('uploading', 'ready', 'failed', 'deleted')", name="status"),
    )
    op.create_index("ix_videos_status", "videos", ["status"])

    op.create_table(
        "clips",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=140), nullable=False),
        sa.Column("start_sec", sa.Float(), nullable=False),
        sa.Column("end_sec", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("features", _json(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], name="fk_clips_video_id_videos", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_clips"),
        sa.CheckConstraint(
            "status IN ('draft', 'render_queued', 'rendering', 'rendered', 'render_failed')",
            name="status",
        ),
        sa.CheckConstraint("end_sec > start_sec", name="time_order"),
        sa.CheckConstraint("start_sec >= 0", name="start_nonneg"),
    )
    op.create_index("ix_clips_video_id_status", "clips", ["video_id", "status"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("ref_type", sa.String(length=16), nullable=False),
        sa.Column("ref_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("payload", _json(), nullable=True),
        sa.Column("result", _json(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
        sa.UniqueConstraint("idempotency_key", name="uq_jobs_idempotency_key"),
        sa.CheckConstraint(
            "type IN ('transcribe', 'render', 'text_gen', 'publish', 'metrics_sync', 'train')",
            name="type",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'retrying', 'cancelled')",
            name="status",
        ),
    )
    op.create_index("ix_jobs_status_type", "jobs", ["status", "type"])
    op.create_index("ix_jobs_ref", "jobs", ["ref_type", "ref_id"])

    op.create_table(
        "rendered_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clip_id", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("codec_video", sa.String(length=16), nullable=False),
        sa.Column("codec_audio", sa.String(length=16), nullable=False),
        sa.Column("pix_fmt", sa.String(length=16), nullable=False),
        sa.Column("duration_sec", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["clip_id"], ["clips.id"], name="fk_rendered_assets_clip_id_clips", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_rendered_assets"),
        sa.UniqueConstraint("storage_key", name="uq_rendered_assets_storage_key"),
        sa.CheckConstraint("status IN ('rendering', 'ready', 'failed')", name="status"),
    )
    op.create_index("ix_rendered_assets_clip_id", "rendered_assets", ["clip_id"])

    op.create_table(
        "platform_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("external_account_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("credentials_encrypted", sa.Text(), nullable=False),
        sa.Column("scopes", _json(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_platform_accounts"),
        sa.UniqueConstraint(
            "platform", "external_account_id", name="uq_platform_accounts_platform_external_account_id"
        ),
        sa.CheckConstraint("platform IN ('youtube', 'tiktok')", name="platform"),
    )
    op.create_index("ix_platform_accounts_platform_is_active", "platform_accounts", ["platform", "is_active"])

    op.create_table(
        "publications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clip_id", sa.Uuid(), nullable=False),
        sa.Column("rendered_asset_id", sa.Uuid(), nullable=True),
        sa.Column("platform_account_id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("external_post_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("metadata", _json(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["clip_id"], ["clips.id"], name="fk_publications_clip_id_clips", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["rendered_asset_id"], ["rendered_assets.id"],
            name="fk_publications_rendered_asset_id_rendered_assets", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["platform_account_id"], ["platform_accounts.id"],
            name="fk_publications_platform_account_id_platform_accounts", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_publications"),
        sa.UniqueConstraint("idempotency_key", name="uq_publications_idempotency_key"),
        sa.CheckConstraint("platform IN ('youtube', 'tiktok')", name="platform"),
        sa.CheckConstraint(
            "status IN ('draft', 'scheduled', 'uploading', 'published', 'failed', 'cancelled')",
            name="status",
        ),
    )
    op.create_index("ix_publications_clip_platform_status", "publications", ["clip_id", "platform", "status"])
    op.create_index(
        "uq_publications_active", "publications", ["clip_id", "platform"], unique=True,
        postgresql_where=sa.text("status NOT IN ('cancelled', 'failed')"),
        sqlite_where=sa.text("status NOT IN ('cancelled', 'failed')"),
    )


def downgrade() -> None:
    op.drop_index("uq_publications_active", table_name="publications")
    op.drop_index("ix_publications_clip_platform_status", table_name="publications")
    op.drop_table("publications")
    op.drop_index("ix_platform_accounts_platform_is_active", table_name="platform_accounts")
    op.drop_table("platform_accounts")
    op.drop_index("ix_rendered_assets_clip_id", table_name="rendered_assets")
    op.drop_table("rendered_assets")
    op.drop_index("ix_jobs_ref", table_name="jobs")
    op.drop_index("ix_jobs_status_type", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_clips_video_id_status", table_name="clips")
    op.drop_table("clips")
    op.drop_index("ix_videos_status", table_name="videos")
    op.drop_table("videos")
