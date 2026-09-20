"""Publication + PlatformAccount API schemas."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import DateTimeUtc

PlatformL = Literal["youtube", "tiktok"]
PrivacyL = Literal["public", "unlisted", "private"]


class ManualPublishCreate(BaseModel):
    clip_id: UUID
    platform: PlatformL
    platform_account_id: UUID
    title: str = Field(min_length=1, max_length=2200)
    description: str | None = Field(default=None, max_length=5000)
    privacy: PrivacyL = "public"
    scheduled_at: DateTimeUtc | None = None


class PublicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clip_id: UUID
    rendered_asset_id: UUID | None = None
    platform_account_id: UUID
    platform: PlatformL
    external_post_id: str | None = None
    status: str
    scheduled_at: DateTimeUtc | None = None
    published_at: DateTimeUtc | None = None
    idempotency_key: str
    attempt_count: int
    last_error: str | None = None
    metadata: dict | None = Field(default=None, validation_alias="meta")
    created_at: DateTimeUtc
    updated_at: DateTimeUtc


class PublicationPage(BaseModel):
    items: list[PublicationRead]
    total: int


class PlatformAccountCreate(BaseModel):
    platform: PlatformL
    external_account_id: str = Field(min_length=1, max_length=255)
    display_name: str | None = None
    credentials: dict  # {"access_token": ...} — encrypted at rest, never returned
    scopes: list[str] = Field(default_factory=list)


class PlatformAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    platform: PlatformL
    external_account_id: str
    display_name: str | None = None
    credentials: str = "***"  # masked, always
    scopes: list
    is_active: bool
    created_at: DateTimeUtc
    updated_at: DateTimeUtc


class PlatformAccountPage(BaseModel):
    items: list[PlatformAccountRead]
    total: int
