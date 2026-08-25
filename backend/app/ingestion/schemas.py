from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class VideoResponse(BaseModel):
    id: UUID
    original_filename: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
