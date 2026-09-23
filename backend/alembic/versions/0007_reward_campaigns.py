"""Content Rewards campaign foundation (CR-1, CONTRACTS ЧАСТЬ CR v2.1)

4 tables: reward_campaigns, campaign_terms_versions, campaign_brief_versions,
campaign_source_assets. Circular pointers (current_terms_version_id,
active_brief_version_id) are added AFTER the dependent tables exist via
batch ALTER (native ALTER on PostgreSQL, copy-and-move on SQLite).

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOW = sa.text("CURRENT_TIMESTAMP")


def _json() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "reward_campaigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("external_campaign_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("brand_name", sa.String(255), nullable=True),
        sa.Column("source_url", sa.String(1024), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("platforms", _json(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("budget_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("budget_spent", sa.Numeric(14, 2), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("imported_payload", _json(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_reward_campaigns"),
        sa.UniqueConstraint(
            "provider", "external_campaign_id",
            name="uq_reward_campaigns_provider_external_campaign_id",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'closed', 'unknown')", name="status"
        ),
        sa.CheckConstraint("length(currency) = 3", name="currency_len"),
    )

    op.create_table(
        "campaign_terms_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("payout_model", sa.String(16), nullable=False),
        sa.Column("cpm_rate", sa.Numeric(10, 4), nullable=True),
        sa.Column("per_post_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("retainer_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("retainer_cycle_days", sa.Integer(), nullable=True),
        sa.Column("min_payout", sa.Numeric(14, 2), nullable=True),
        sa.Column("max_payout_per_clip", sa.Numeric(14, 2), nullable=True),
        sa.Column("creator_fee_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("fee_free_budget_threshold", sa.Numeric(14, 2), nullable=False),
        sa.Column("earnings_window_days", sa.Integer(), nullable=False),
        sa.Column("payout_hold_days", sa.Integer(), nullable=False),
        sa.Column("submission_deadline_minutes", sa.Integer(), nullable=False),
        sa.Column("terms_source_url", sa.String(1024), nullable=False),
        sa.Column("terms_checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_campaign_terms_versions"),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["reward_campaigns.id"], ondelete="CASCADE",
            name="fk_campaign_terms_versions_campaign_id_reward_campaigns",
        ),
        sa.UniqueConstraint(
            "campaign_id", "version",
            name="uq_campaign_terms_versions_campaign_id_version",
        ),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint("payout_model IN ('cpm', 'per_post', 'retainer')", name="payout_model"),
        sa.CheckConstraint(
            "(payout_model = 'cpm' AND cpm_rate IS NOT NULL AND per_post_amount IS NULL "
            "AND retainer_amount IS NULL AND retainer_cycle_days IS NULL) OR "
            "(payout_model = 'per_post' AND per_post_amount IS NOT NULL AND cpm_rate IS NULL "
            "AND retainer_amount IS NULL AND retainer_cycle_days IS NULL) OR "
            "(payout_model = 'retainer' AND retainer_amount IS NOT NULL "
            "AND retainer_cycle_days IS NOT NULL AND cpm_rate IS NULL AND per_post_amount IS NULL)",
            name="payout_model_fields",
        ),
        sa.CheckConstraint(
            "max_payout_per_clip IS NULL OR min_payout IS NULL OR max_payout_per_clip >= min_payout",
            name="payout_bounds",
        ),
        sa.CheckConstraint(
            "creator_fee_percent >= 0 AND creator_fee_percent <= 100", name="fee_percent_range"
        ),
        sa.CheckConstraint(
            "(cpm_rate IS NULL OR cpm_rate > 0) AND (per_post_amount IS NULL OR per_post_amount > 0) "
            "AND (retainer_amount IS NULL OR retainer_amount > 0) "
            "AND (min_payout IS NULL OR min_payout >= 0) "
            "AND (max_payout_per_clip IS NULL OR max_payout_per_clip > 0) "
            "AND fee_free_budget_threshold >= 0",
            name="amounts_positive",
        ),
        sa.CheckConstraint(
            "earnings_window_days > 0 AND payout_hold_days >= 0 AND submission_deadline_minutes > 0 "
            "AND (retainer_cycle_days IS NULL OR retainer_cycle_days > 0)",
            name="windows_positive",
        ),
    )
    op.create_index(
        "ix_campaign_terms_versions_campaign_id", "campaign_terms_versions", ["campaign_id"]
    )

    op.create_table(
        "campaign_brief_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("raw_file_key", sa.String(512), nullable=True),
        sa.Column("structured_json", _json(), nullable=True),
        sa.Column("source_url", sa.String(1024), nullable=False),
        sa.Column("checklist", _json(), nullable=True),
        sa.Column("parser_engine", sa.String(32), nullable=False),
        sa.Column("parser_confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("supersedes_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_campaign_brief_versions"),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["reward_campaigns.id"], ondelete="CASCADE",
            name="fk_campaign_brief_versions_campaign_id_reward_campaigns",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"], ["campaign_brief_versions.id"], ondelete="SET NULL",
            name="fk_campaign_brief_versions_supersedes_id_campaign_brief_versions",
        ),
        sa.UniqueConstraint(
            "campaign_id", "version",
            name="uq_campaign_brief_versions_campaign_id_version",
        ),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint(
            "status IN ('pending_approval', 'approved', 'rejected', 'superseded')", name="status"
        ),
        sa.CheckConstraint(
            "raw_text IS NOT NULL OR raw_file_key IS NOT NULL OR structured_json IS NOT NULL",
            name="source_present",
        ),
    )
    op.create_index(
        "ix_campaign_brief_versions_campaign_id", "campaign_brief_versions", ["campaign_id"]
    )

    op.create_table(
        "campaign_source_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("brief_version_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=True),
        sa.Column("external_url", sa.String(1024), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("authorized", sa.Boolean(), nullable=False),
        sa.Column("authorization_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_campaign_source_assets"),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["reward_campaigns.id"], ondelete="CASCADE",
            name="fk_campaign_source_assets_campaign_id_reward_campaigns",
        ),
        sa.ForeignKeyConstraint(
            ["brief_version_id"], ["campaign_brief_versions.id"], ondelete="CASCADE",
            name="fk_campaign_source_assets_brief_version_id_campaign_brief_versions",
        ),
        sa.CheckConstraint("kind IN ('video', 'audio', 'image', 'link')", name="kind"),
        sa.CheckConstraint(
            "storage_key IS NOT NULL OR external_url IS NOT NULL", name="location_present"
        ),
    )
    op.create_index(
        "ix_campaign_source_assets_campaign_id", "campaign_source_assets", ["campaign_id"]
    )

    # Circular FK resolution (v2.1): add version pointers AFTER dependent tables exist.
    # batch_alter_table -> native ALTER on PostgreSQL, copy-and-move on SQLite.
    with op.batch_alter_table("reward_campaigns") as batch:
        batch.add_column(sa.Column("current_terms_version_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("active_brief_version_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_reward_campaigns_current_terms_version_id_campaign_terms_versions",
            "campaign_terms_versions",
            ["current_terms_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_reward_campaigns_active_brief_version_id_campaign_brief_versions",
            "campaign_brief_versions",
            ["active_brief_version_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    # Drop circular FK pointers first (PG refuses DROP TABLE with dependent FKs).
    with op.batch_alter_table("reward_campaigns") as batch:
        batch.drop_constraint(
            "fk_reward_campaigns_current_terms_version_id_campaign_terms_versions",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "fk_reward_campaigns_active_brief_version_id_campaign_brief_versions",
            type_="foreignkey",
        )
        batch.drop_column("current_terms_version_id")
        batch.drop_column("active_brief_version_id")
    op.drop_index("ix_campaign_source_assets_campaign_id", table_name="campaign_source_assets")
    op.drop_table("campaign_source_assets")
    op.drop_index("ix_campaign_brief_versions_campaign_id", table_name="campaign_brief_versions")
    op.drop_table("campaign_brief_versions")
    op.drop_index("ix_campaign_terms_versions_campaign_id", table_name="campaign_terms_versions")
    op.drop_table("campaign_terms_versions")
    op.drop_table("reward_campaigns")
