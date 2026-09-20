"""Shared schema helpers. ISO8601 UTC dates with Z suffix (CONTRACTS §1)."""
from datetime import datetime, timezone
from typing import Annotated

from pydantic import PlainSerializer


def _dt_to_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


DateTimeUtc = Annotated[datetime, PlainSerializer(_dt_to_z, return_type=str, when_used="always")]
