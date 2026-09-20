"""RenderedAsset API schemas."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.common import DateTimeUtc


class RenderedAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clip_id: UUID
    storage_key: str
    size_bytes: int
    width: int
    height: int
    codec_video: str
    codec_audio: str
    pix_fmt: str
    duration_sec: float
    status: str
    created_at: DateTimeUtc


class PresignedUrl(BaseModel):
    url: str
    expires_sec: int
