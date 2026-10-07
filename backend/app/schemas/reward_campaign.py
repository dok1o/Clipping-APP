"""Content Rewards API schemas (CR-1: campaign foundation + brief import).

Money rules (CR-0.4): request money fields are `Decimal` (pydantic-core parses
JSON numbers into Decimal without float math); responses serialize money as
exact decimal STRINGS to avoid float precision loss in JSON.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator

from app.schemas.common import DateTimeUtc

# --- money field types -------------------------------------------------------
Amount14_2 = Annotated[Decimal, Field(max_digits=14, decimal_places=2)]
Rate10_4 = Annotated[Decimal, Field(max_digits=10, decimal_places=4)]
Percent5_2 = Annotated[Decimal, Field(max_digits=5, decimal_places=2)]
Confidence4_3 = Annotated[Decimal, Field(max_digits=4, decimal_places=3)]
MoneyOut = Annotated[Decimal, PlainSerializer(lambda v: format(v, "f"), return_type=str)]

PayoutModelLit = Literal["cpm", "per_post", "retainer"]
PlatformLit = Literal["tiktok", "youtube", "instagram", "x"]
AssetKindLit = Literal["video", "audio", "image", "link"]
CampaignStatusLit = Literal["draft", "active", "paused", "closed", "unknown"]


# --- requests -----------------------------------------------------------------
class TermsInput(BaseModel):
    payout_model: PayoutModelLit
    cpm_rate: Rate10_4 | None = None
    per_post_amount: Amount14_2 | None = None
    retainer_amount: Amount14_2 | None = None
    retainer_cycle_days: int | None = Field(default=None, ge=1)
    min_payout: Amount14_2 | None = None
    max_payout_per_clip: Amount14_2 | None = None
    creator_fee_percent: Percent5_2
    fee_free_budget_threshold: Amount14_2
    earnings_window_days: int = Field(ge=1)
    payout_hold_days: int = Field(ge=0)
    submission_deadline_minutes: int = Field(ge=1)
    terms_source_url: str = Field(min_length=1, max_length=1024)
    terms_checked_at: datetime | None = None  # default: now (UTC)


class SourceAssetInput(BaseModel):
    kind: AssetKindLit
    title: str = Field(min_length=1, max_length=255)
    external_url: str | None = Field(default=None, min_length=1, max_length=1024)
    storage_key: str | None = Field(default=None, min_length=1, max_length=512)
    sha256: str | None = Field(default=None, min_length=64, max_length=64)


class BriefInput(BaseModel):
    raw_text: str | None = Field(default=None, min_length=1)
    structured_json: dict[str, Any] | None = None
    source_url: str | None = Field(default=None, min_length=1, max_length=1024)
    source_assets: list[SourceAssetInput] = Field(default_factory=list)


class CampaignImportRequest(BaseModel):
    """JSON import: campaign identity + optional terms + optional brief.

    Deterministic by (provider, external_campaign_id): re-import updates the
    operational snapshot, never duplicates the campaign; identical terms/brief
    content does not create new versions.
    """

    provider: str = Field(default="whop_content_rewards", min_length=1, max_length=32)
    external_campaign_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    source_url: str = Field(min_length=1, max_length=1024)
    brand_name: str | None = Field(default=None, max_length=255)
    status: CampaignStatusLit = "draft"
    platforms: list[PlatformLit] = Field(default_factory=list)
    currency: str = "USD"
    budget_total: Amount14_2 | None = None
    budget_spent: Amount14_2 | None = None
    deadline_at: datetime | None = None
    imported_payload: dict[str, Any] | None = None
    terms: TermsInput | None = None
    brief: BriefInput | None = None

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 3 or not v.isalpha():
            raise ValueError("currency must be a 3-letter ISO-4217 code")
        return v


class TextImportRequest(CampaignImportRequest):
    """Text import: same campaign fields, brief arrives as plain text."""

    raw_text: str = Field(min_length=1)  # brief raw text
    brief_source_url: str | None = Field(default=None, min_length=1, max_length=1024)
    brief_source_assets: list[SourceAssetInput] = Field(default_factory=list)


class TermsCreate(TermsInput):
    """POST /reward-campaigns/{id}/terms — new immutable version."""


class TermsConfirm(BaseModel):
    """PATCH /reward-campaigns/{id}/terms — explicit user confirmation."""

    version_id: uuid.UUID
    confirm: bool = True


class BriefCreate(BaseModel):
    """POST /reward-campaigns/{id}/brief — new version (pending_approval)."""

    raw_text: str | None = Field(default=None, min_length=1)
    structured_json: dict[str, Any] | None = None
    source_url: str | None = Field(default=None, min_length=1, max_length=1024)
    source_assets: list[SourceAssetInput] = Field(default_factory=list)


class BriefDecision(BaseModel):
    """PATCH /reward-campaigns/{id}/brief — approve/reject (explicit user action)."""

    version_id: uuid.UUID
    action: Literal["approve", "reject"]


# --- responses ----------------------------------------------------------------
class TermsVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    campaign_id: uuid.UUID
    version: int
    content_hash: str
    payout_model: str
    cpm_rate: MoneyOut | None = None
    per_post_amount: MoneyOut | None = None
    retainer_amount: MoneyOut | None = None
    retainer_cycle_days: int | None = None
    min_payout: MoneyOut | None = None
    max_payout_per_clip: MoneyOut | None = None
    creator_fee_percent: MoneyOut
    fee_free_budget_threshold: MoneyOut
    earnings_window_days: int
    payout_hold_days: int
    submission_deadline_minutes: int
    terms_source_url: str
    terms_checked_at: DateTimeUtc
    confirmed_at: DateTimeUtc | None = None
    created_at: DateTimeUtc


class SourceAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    campaign_id: uuid.UUID
    brief_version_id: uuid.UUID
    kind: str
    storage_key: str | None = None
    external_url: str | None = None
    sha256: str | None = None
    title: str
    authorized: bool
    authorization_note: str | None = None
    created_at: DateTimeUtc


class BriefVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    campaign_id: uuid.UUID
    version: int
    status: str
    raw_text: str | None = None
    raw_file_key: str | None = None
    structured_json: dict[str, Any] | None = None
    source_url: str
    parser_engine: str
    parser_confidence: MoneyOut | None = None
    supersedes_id: uuid.UUID | None = None
    approved_at: DateTimeUtc | None = None
    created_at: DateTimeUtc
    assets: list[SourceAssetRead] = Field(default_factory=list)


class RewardCampaignRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    external_campaign_id: str
    name: str
    brand_name: str | None = None
    source_url: str
    status: str
    platforms: list[str] | None = None
    currency: str
    budget_total: MoneyOut | None = None
    budget_spent: MoneyOut | None = None
    deadline_at: DateTimeUtc | None = None
    current_terms_version_id: uuid.UUID | None = None
    active_brief_version_id: uuid.UUID | None = None
    created_at: DateTimeUtc
    updated_at: DateTimeUtc


class CampaignPage(BaseModel):
    items: list[RewardCampaignRead]
    total: int


class ImportResultRead(BaseModel):
    campaign: RewardCampaignRead
    created: bool
    terms_version: TermsVersionRead | None = None
    terms_created: bool = False
    brief_version: BriefVersionRead | None = None
    brief_created: bool = False


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
