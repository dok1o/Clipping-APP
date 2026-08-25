"""create core domain tables

Revision ID: 20260825_0001
Revises:
Create Date: 2026-08-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260825_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "videos",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_path", sa.String(length=1024), nullable=True),
        sa.Column("storage_key", sa.String(length=1024), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_videos_status"), "videos", ["status"], unique=False)
    op.create_index(op.f("ix_videos_storage_key"), "videos", ["storage_key"], unique=False)

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_jobs_entity_id"), "jobs", ["entity_id"], unique=False)
    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"], unique=False)
    op.create_index(op.f("ix_jobs_type"), "jobs", ["type"], unique=False)

    op.create_table(
        "platform_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("external_account_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("encrypted_credentials", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_platform_accounts_external_account_id"), "platform_accounts", ["external_account_id"], unique=False)
    op.create_index(op.f("ix_platform_accounts_platform"), "platform_accounts", ["platform"], unique=False)
    op.create_index(
        "ix_platform_accounts_platform_external_account_id",
        "platform_accounts",
        ["platform", "external_account_id"],
        unique=False,
    )
    op.create_index(op.f("ix_platform_accounts_status"), "platform_accounts", ["status"], unique=False)

    op.create_table(
        "clips",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("start", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("end", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_clips_status"), "clips", ["status"], unique=False)
    op.create_index(op.f("ix_clips_video_id"), "clips", ["video_id"], unique=False)

    op.create_table(
        "rendered_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("clip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("format", sa.String(length=32), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("duration", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["clip_id"], ["clips.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_rendered_assets_clip_id"), "rendered_assets", ["clip_id"], unique=False)
    op.create_index(op.f("ix_rendered_assets_storage_key"), "rendered_assets", ["storage_key"], unique=False)

    op.create_table(
        "publications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("clip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_post_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["platform_accounts.id"]),
        sa.ForeignKeyConstraint(["clip_id"], ["clips.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_publications_account_id"), "publications", ["account_id"], unique=False)
    op.create_index(op.f("ix_publications_clip_id"), "publications", ["clip_id"], unique=False)
    op.create_index(op.f("ix_publications_external_post_id"), "publications", ["external_post_id"], unique=False)
    op.create_index(op.f("ix_publications_status"), "publications", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_publications_status"), table_name="publications")
    op.drop_index(op.f("ix_publications_external_post_id"), table_name="publications")
    op.drop_index(op.f("ix_publications_clip_id"), table_name="publications")
    op.drop_index(op.f("ix_publications_account_id"), table_name="publications")
    op.drop_table("publications")

    op.drop_index(op.f("ix_rendered_assets_storage_key"), table_name="rendered_assets")
    op.drop_index(op.f("ix_rendered_assets_clip_id"), table_name="rendered_assets")
    op.drop_table("rendered_assets")

    op.drop_index(op.f("ix_clips_video_id"), table_name="clips")
    op.drop_index(op.f("ix_clips_status"), table_name="clips")
    op.drop_table("clips")

    op.drop_index(op.f("ix_platform_accounts_status"), table_name="platform_accounts")
    op.drop_index("ix_platform_accounts_platform_external_account_id", table_name="platform_accounts")
    op.drop_index(op.f("ix_platform_accounts_platform"), table_name="platform_accounts")
    op.drop_index(op.f("ix_platform_accounts_external_account_id"), table_name="platform_accounts")
    op.drop_table("platform_accounts")

    op.drop_index(op.f("ix_jobs_type"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_status"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_entity_id"), table_name="jobs")
    op.drop_table("jobs")

    op.drop_index(op.f("ix_videos_storage_key"), table_name="videos")
    op.drop_index(op.f("ix_videos_status"), table_name="videos")
    op.drop_table("videos")
