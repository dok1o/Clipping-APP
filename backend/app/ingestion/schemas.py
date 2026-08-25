from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VideoResponse(BaseModel):
    id: UUID
    original_filename: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClipCreate(BaseModel):
    start: float = Field(ge=0)
    end: float

    @model_validator(mode="after")
    def validate_timestamp_order(self) -> "ClipCreate":
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class ClipResponse(BaseModel):
    id: UUID
    video_id: UUID
    start: float
    end: float
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
