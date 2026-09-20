"""Publisher interface — the extension point for platforms (master spec §6, §15).

Adding a second platform (YouTube) must not touch publish_service core logic:
implement this interface and register it in the publisher registry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class PublishRequest:
    video_path: str  # local tmp file with the rendered asset
    title: str
    description: str | None = None
    privacy: str = "public"  # our unified enum: public | unlisted | private
    tags: list[str] = field(default_factory=list)


@dataclass
class PublishResult:
    external_post_id: str  # platform-side id (publish_id / video id)
    status: str  # published | processing
    raw: dict = field(default_factory=dict)  # sanitized raw response (no secrets)


class PlatformError(Exception):
    """Controlled platform failure: message must be secret-free."""

    def __init__(self, code: str, message: str, raw: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.raw = raw or {}


class Publisher(Protocol):
    platform: str

    def publish(self, request: PublishRequest, credentials: dict) -> PublishResult:
        """Upload + publish; raises PlatformError on failure (never leaks secrets)."""
        ...  # pragma: no cover

    def check_status(self, external_post_id: str, credentials: dict) -> str:
        """Return processing | published | failed for an earlier publish."""
        ...  # pragma: no cover


# --- Publisher registry (moved from tiktok.py: platform-neutral home) ---

_PUBLISHERS: dict[str, type] = {}


def register_publisher(cls: type) -> type:
    """Register a Publisher implementation by its `platform` attribute."""
    _PUBLISHERS[cls.platform] = cls
    return cls


def _ensure_adapters_loaded() -> None:
    """Import adapter modules so their publishers self-register (no cycles)."""
    import app.services.publish.tiktok  # noqa: F401  (registers TikTokPublisher)
    import app.services.publish.youtube  # noqa: F401  (registers YouTubePublisher)


def get_publisher(platform: str, **kwargs):
    """Resolve a publisher instance for a platform (test kwargs pass through)."""
    _ensure_adapters_loaded()
    cls = _PUBLISHERS.get(platform)
    if cls is None:
        raise PlatformError("unsupported_platform", f"No publisher for platform '{platform}'")
    return cls(**kwargs)
