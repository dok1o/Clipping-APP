"""TikTok Content Posting API adapter (Direct Post, FILE_UPLOAD).

Implemented strictly per the official documentation (see docs/KNOWLEDGE.md §2,
checked 2026-09-20):
  1. POST /v2/post/publish/video/init/         (scope video.publish)
  2. PUT  {upload_url}  with Content-Range      (single chunk for our sizes)
  3. POST /v2/post/publish/status/fetch/        (poll until terminal status)
"""
from __future__ import annotations

import time
from pathlib import Path

import httpx

from app.core.logging import get_logger
from app.services.publish.base import PlatformError, PublishRequest, PublishResult

logger = get_logger(__name__)

DEFAULT_BASE_URL = "https://open.tiktokapis.com"
TITLE_MAX_CHARS = 2200  # caption limit per docs/guides (KNOWLEDGE §2)
SINGLE_CHUNK_LIMIT = 64 * 1024 * 1024  # files up to 64MB go as a single chunk

PRIVACY_MAP = {
    "public": "PUBLIC_TO_EVERYONE",
    "unlisted": "MUTUAL_FOLLOW_FRIENDS",  # TikTok has no unlisted (fixed in CONTRACTS)
    "private": "SELF_ONLY",
}

STATUS_PUBLISHED = "published"
STATUS_PROCESSING = "processing"
STATUS_FAILED = "failed"


class TikTokPublisher:
    platform = "tiktok"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout_sec: float = 60.0,
        transport: "httpx.BaseTransport | None" = None,  # test injection point
        poll_delay_sec: float = 1.0,  # override in tests
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec
        self.transport = transport
        self.poll_delay_sec = poll_delay_sec

    # --- public API ---

    def publish(self, request: PublishRequest, credentials: dict) -> PublishResult:
        access_token = self._require_token(credentials)
        title = self._build_title(request)

        video_size = Path(request.video_path).stat().st_size
        chunk_size = min(video_size, SINGLE_CHUNK_LIMIT)
        total_chunks = 1 if video_size <= SINGLE_CHUNK_LIMIT else -1  # -1 => not needed at our sizes

        init_payload = {
            "post_info": {
                "title": title,
                "privacy_level": PRIVACY_MAP[request.privacy],
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": chunk_size,
                "total_chunk_count": 1 if total_chunks == 1 else (video_size + chunk_size - 1) // chunk_size,
            },
        }

        with httpx.Client(timeout=self.timeout_sec, transport=self.transport) as client:
            init = self._init_post(client, init_payload, access_token)
            publish_id = init["publish_id"]
            upload_url = init["upload_url"]
            self._upload_file(client, upload_url, Path(request.video_path), access_token)
            status = self._poll_status(client, publish_id, access_token)

        if status == "FAILED":
            raise PlatformError("publish_failed", f"TikTok reported FAILED for {publish_id}")
        result_status = STATUS_PUBLISHED if status == "PUBLISH_COMPLETE" else STATUS_PROCESSING
        return PublishResult(external_post_id=publish_id, status=result_status, raw={"status": status})

    def check_status(self, external_post_id: str, credentials: dict) -> str:
        access_token = self._require_token(credentials)
        with httpx.Client(timeout=self.timeout_sec, transport=self.transport) as client:
            status = self._fetch_status(client, external_post_id, access_token)
        if status == "FAILED":
            return STATUS_FAILED
        return STATUS_PUBLISHED if status == "PUBLISH_COMPLETE" else STATUS_PROCESSING

    # --- helpers ---

    @staticmethod
    def _require_token(credentials: dict) -> str:
        token = (credentials or {}).get("access_token")
        if not token:
            raise PlatformError("missing_credentials", "PlatformAccount has no access_token")
        return token

    @staticmethod
    def _build_title(request: PublishRequest) -> str:
        title = request.title.strip()
        if request.description:
            title = f"{title}\n{request.description}" if len(title) < TITLE_MAX_CHARS else title
        if request.tags:
            tags = " ".join(f"#{t.lstrip('#')}" for t in request.tags)
            title = f"{title[: TITLE_MAX_CHARS - len(tags) - 1]} {tags}".strip()
        if not title:
            raise PlatformError("invalid_title", "Empty title")
        if len(title) > TITLE_MAX_CHARS:
            title = title[:TITLE_MAX_CHARS]
        return title

    def _init_post(self, client: httpx.Client, payload: dict, token: str) -> dict:
        try:
            response = client.post(
                f"{self.base_url}/v2/post/publish/video/init/",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as exc:
            raise PlatformError("network_error", f"TikTok init request failed: {exc}") from exc
        body = self._parse(response, "init")
        data = body.get("data") or {}
        if not data.get("publish_id"):
            raise PlatformError("publish_failed", "TikTok init returned no publish_id", body)
        if "upload_url" not in data:
            raise PlatformError("publish_failed", "TikTok init returned no upload_url", body)
        return data

    def _upload_file(self, client: httpx.Client, upload_url: str, path: Path, token: str) -> None:
        size = path.stat().st_size
        headers = {
            "Content-Type": "video/mp4",
            "Content-Length": str(size),
            "Content-Range": f"bytes 0-{size - 1}/{size}",
        }
        try:
            with open(path, "rb") as fh:
                response = client.put(upload_url, content=fh.read(), headers=headers)
        except httpx.HTTPError as exc:
            raise PlatformError("network_error", f"TikTok upload failed: {exc}") from exc
        if response.status_code not in (200, 201, 204):
            raise PlatformError(
                "upload_failed",
                f"TikTok upload returned HTTP {response.status_code}",
                {"body": response.text[:500]},
            )

    def _poll_status(self, client: httpx.Client, publish_id: str, token: str, attempts: int = 6) -> str:
        """Poll a few times with backoff; long processing => 'processing' (checked later)."""
        last = "PROCESSING_UPLOAD"
        for attempt in range(attempts):
            last = self._fetch_status(client, publish_id, token)
            if last in ("PUBLISH_COMPLETE", "FAILED"):
                return last
            time.sleep(min(self.poll_delay_sec * (2**attempt), 10))
        return last

    def _fetch_status(self, client: httpx.Client, publish_id: str, token: str) -> str:
        try:
            response = client.post(
                f"{self.base_url}/v2/post/publish/status/fetch/",
                json={"publish_id": publish_id},
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as exc:
            raise PlatformError("network_error", f"TikTok status request failed: {exc}") from exc
        body = self._parse(response, "status")
        return (body.get("data") or {}).get("status", "")

    def _parse(self, response: httpx.Response, stage: str) -> dict:
        try:
            body = response.json()
        except ValueError:
            raise PlatformError(
                "invalid_response", f"TikTok {stage}: non-JSON response HTTP {response.status_code}"
            ) from None
        error = body.get("error") or {}
        if response.status_code != 200 or (error.get("code") not in (None, "ok")):
            code = error.get("code") or f"http_{response.status_code}"
            message = error.get("message") or f"TikTok {stage} failed"
            raise PlatformError(code, message, body)
        return body


# --- registry (extension point for the second platform) ---

from app.services.publish.base import register_publisher  # noqa: E402  (registry moved to base)


register_publisher(TikTokPublisher)


from app.services.publish.base import get_publisher as get_publisher  # re-export (compat)
