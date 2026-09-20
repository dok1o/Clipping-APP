"""Text generation API schemas (CONTRACTS §4.12)."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

PlatformL = Literal["youtube", "tiktok"]


class TextGenCreate(BaseModel):
    clip_id: UUID
    platform: PlatformL
    tone: str | None = Field(default=None, max_length=120)
    transcript: str | None = Field(default=None, max_length=20000)


class GeneratedTextsOut(BaseModel):
    titles: list[str]
    description: str
    hashtags: list[str]


class TextGenResult(BaseModel):
    """job_id is null in Stage 2 (synchronous); Stage 5 may return a real job id —
    the contract carries both fields (spec §16)."""

    job_id: UUID | None = None
    texts: GeneratedTextsOut
    captions_srt: str = ""
    platform: PlatformL
