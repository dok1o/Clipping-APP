from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RenderedAssetResponse(BaseModel):
    id: UUID
    clip_id: UUID
    storage_key: str
    format: str
    width: int
    height: int
    duration: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
