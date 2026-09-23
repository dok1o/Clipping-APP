"""Content Rewards: campaign foundation (CONTRACTS ЧАСТЬ CR v2.1, migration 0007).

Economic terms live ONLY in `campaign_terms_versions` (immutable, INSERT-only);
`reward_campaigns` keeps identity/status/platforms/currency/budget snapshots
and version pointers (added via ALTER in 0007 — circular FK campaign<->terms).
Money: Numeric(14,2) amounts, Numeric(10,4) CPM rates, Numeric(5,2) percents;
Decimal only in Python, no floats (CR-0.4).
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RewardCampaignStatus:
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class PayoutModel:
    CPM = "cpm"
    PER_POST = "per_post"
    RETAINER = "retainer"


class CampaignTermsStatus:  # brief version lifecycle (no auto-activation, CR-1)
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class SourceAssetKind:
    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"
    LINK = "link"


def _json() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


class RewardCampaign(Base):
    """A monetization campaign imported from a provider (e.g. Whop Content Rewards).

    NOTE (v2.1): NO economic term fields here — payout_model/rates/amounts live
    exclusively in immutable `campaign_terms_versions`.
    """

    __tablename__ = "reward_campaigns"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    external_campaign_id: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    brand_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    source_url: Mapped[str] = mapped_column(sa.String(1024), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, default=RewardCampaignStatus.DRAFT
    )
    platforms: Mapped[list[str] | None] = mapped_column(_json(), nullable=True)
    currency: Mapped[str] = mapped_column(sa.String(3), nullable=False, default="USD")
    # Operational budget snapshot (NOT terms; CR-6 reads it from here)
    budget_total: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2), nullable=True)
    budget_spent: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    imported_payload: Mapped[dict[str, Any] | None] = mapped_column(_json(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()
    )
    # Pointers to confirmed/approved versions — declared LAST to match the
    # migration column order (0007 adds them via ALTER after the table exists).
    current_terms_version_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("campaign_terms_versions.id", ondelete="SET NULL"), nullable=True
    )
    active_brief_version_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("campaign_brief_versions.id", ondelete="SET NULL"), nullable=True
    )

    terms_versions: Mapped[list["CampaignTermsVersion"]] = relationship(
        back_populates="campaign",
        foreign_keys="CampaignTermsVersion.campaign_id",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    brief_versions: Mapped[list["CampaignBriefVersion"]] = relationship(
        back_populates="campaign",
        foreign_keys="CampaignBriefVersion.campaign_id",
        cascade="save-update, merge",
        passive_deletes=True,
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "provider", "external_campaign_id",
            name="uq_reward_campaigns_provider_external_campaign_id",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'closed', 'unknown')",
            name="status",
        ),
        sa.CheckConstraint("length(currency) = 3", name="currency_len"),
    )


class CampaignTermsVersion(Base):
    """Immutable economic terms of a campaign (single source of pricing truth).

    Rows are INSERT-only; changing terms means a NEW version with a new
    content_hash. Only fields relevant to payout_model may be non-NULL
    (enforced by DB CHECK `payout_model_fields` + service validation).
    """

    __tablename__ = "campaign_terms_versions"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("reward_campaigns.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    content_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    payout_model: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    # cpm model
    cpm_rate: Mapped[Decimal | None] = mapped_column(sa.Numeric(10, 4), nullable=True)
    # per_post model
    per_post_amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2), nullable=True)
    # retainer model
    retainer_amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2), nullable=True)
    retainer_cycle_days: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    # common bounds (any model)
    min_payout: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2), nullable=True)
    max_payout_per_clip: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2), nullable=True)
    # fee & windows (KNOWLEDGE §7 defaults are confirmed at import, never hardcoded logic)
    creator_fee_percent: Mapped[Decimal] = mapped_column(sa.Numeric(5, 2), nullable=False)
    fee_free_budget_threshold: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2), nullable=False)
    earnings_window_days: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    payout_hold_days: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    submission_deadline_minutes: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    terms_source_url: Mapped[str] = mapped_column(sa.String(1024), nullable=False)
    terms_checked_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    campaign: Mapped[RewardCampaign] = relationship(
        back_populates="terms_versions", foreign_keys=[campaign_id]
    )

    __table_args__ = (
        sa.UniqueConstraint("campaign_id", "version", name="uq_campaign_terms_versions_campaign_id_version"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint(
            "payout_model IN ('cpm', 'per_post', 'retainer')", name="payout_model"
        ),
        # payout_model field matrix (CR v2.1): relevant fields required, others NULL
        sa.CheckConstraint(
            "(payout_model = 'cpm' AND cpm_rate IS NOT NULL AND per_post_amount IS NULL "
            "AND retainer_amount IS NULL AND retainer_cycle_days IS NULL) OR "
            "(payout_model = 'per_post' AND per_post_amount IS NOT NULL AND cpm_rate IS NULL "
            "AND retainer_amount IS NULL AND retainer_cycle_days IS NULL) OR "
            "(payout_model = 'retainer' AND retainer_amount IS NOT NULL AND retainer_cycle_days IS NOT NULL "
            "AND cpm_rate IS NULL AND per_post_amount IS NULL)",
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
        sa.Index("ix_campaign_terms_versions_campaign_id", "campaign_id"),
    )


class CampaignBriefVersion(Base):
    """Versioned campaign brief; import creates pending_approval (no auto-activation)."""

    __tablename__ = "campaign_brief_versions"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("reward_campaigns.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    raw_file_key: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    structured_json: Mapped[dict[str, Any] | None] = mapped_column(_json(), nullable=True)
    source_url: Mapped[str] = mapped_column(sa.String(1024), nullable=False)
    checklist: Mapped[list[dict[str, Any]] | None] = mapped_column(_json(), nullable=True)
    parser_engine: Mapped[str] = mapped_column(sa.String(32), nullable=False, default="manual")
    parser_confidence: Mapped[Decimal | None] = mapped_column(sa.Numeric(4, 3), nullable=True)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("campaign_brief_versions.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    campaign: Mapped[RewardCampaign] = relationship(
        back_populates="brief_versions", foreign_keys=[campaign_id]
    )
    assets: Mapped[list["CampaignSourceAsset"]] = relationship(
        back_populates="brief_version",
        foreign_keys="CampaignSourceAsset.brief_version_id",
        cascade="save-update, merge",
        passive_deletes=True,
    )

    __table_args__ = (
        sa.UniqueConstraint("campaign_id", "version", name="uq_campaign_brief_versions_campaign_id_version"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint(
            "status IN ('pending_approval', 'approved', 'rejected', 'superseded')",
            name="status",
        ),
        # at least one source must be present
        sa.CheckConstraint(
            "raw_text IS NOT NULL OR raw_file_key IS NOT NULL OR structured_json IS NOT NULL",
            name="source_present",
        ),
        sa.Index("ix_campaign_brief_versions_campaign_id", "campaign_id"),
    )


class CampaignSourceAsset(Base):
    """Campaign source material; `authorized=false` until the user explicitly authorizes."""

    __tablename__ = "campaign_source_assets"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("reward_campaigns.id", ondelete="CASCADE"), nullable=False
    )
    brief_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("campaign_brief_versions.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    external_url: Mapped[str | None] = mapped_column(sa.String(1024), nullable=True)
    sha256: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    title: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    authorized: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=False)
    authorization_note: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    brief_version: Mapped[CampaignBriefVersion] = relationship(
        back_populates="assets", foreign_keys=[brief_version_id]
    )

    __table_args__ = (
        sa.CheckConstraint("kind IN ('video', 'audio', 'image', 'link')", name="kind"),
        sa.CheckConstraint(
            "storage_key IS NOT NULL OR external_url IS NOT NULL", name="location_present"
        ),
        sa.Index("ix_campaign_source_assets_campaign_id", "campaign_id"),
    )
