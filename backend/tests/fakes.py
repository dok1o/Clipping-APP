"""Deterministic fakes for the main test suite (publishers, providers)."""
from app.services.publish.base import PlatformError, PublishRequest, PublishResult


class FakePublisher:
    """Configurable fake platform adapter — never touches the network."""

    platform = "tiktok"

    def __init__(self, *, external_post_id="fake-post-1", fail_with=None) -> None:
        self.external_post_id = external_post_id
        self.fail_with = fail_with
        self.calls: list[PublishRequest] = []

    def publish(self, request: PublishRequest, credentials: dict) -> PublishResult:
        self.calls.append(request)
        if self.fail_with is not None:
            raise self.fail_with
        return PublishResult(external_post_id=self.external_post_id, status="published", raw={"fake": True})

    def check_status(self, external_post_id: str, credentials: dict) -> str:
        return "published"
