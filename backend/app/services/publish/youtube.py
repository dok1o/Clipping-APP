"""YouTube Data API v3 adapter (videos.insert, resumable upload).

Implemented strictly per the official documentation (see docs/KNOWLEDGE.md §6,
checked 2026-09-21):
  1. OAuth2:  POST https://oauth2.googleapis.com/token  (grant_type=refresh_token)
  2. Session: POST /upload/youtube/v3/videos?uploadType=resumable&part=snippet,status
              -> 200 + Location: <resumable session URI>
  3. Bytes:   PUT <session URI>  (single-shot on the resumable session;
              protocol-conformant for our clip sizes, see ADR-017)

Raw httpx implementation: google-api-python-client is NOT a dependency
(ARCHITECTURE ADR-017 — heavy client lib for two HTTP calls).
"""
from __future__ import annotations

from pathlib import Path

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.publish.base import (
    PlatformError,
    PublishRequest,
    PublishResult,
    register_publisher,
)

logger = get_logger(__name__)

API_BASE_URL = "https://www.googleapis.com"
UPLOAD_BASE_URL = "https://www.googleapis.com"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"

TITLE_MAX_CHARS = 100  # official snippet.title limit
DESCRIPTION_MAX_CHARS = 5000
TAGS_TOTAL_MAX_CHARS = 500
DEFAULT_CATEGORY_ID = "22"  # People & Blogs (official default in upload guide)

# YouTube natively supports all three of our unified privacy levels
PRIVACY_MAP = {
    "public": "public",
    "unlisted": "unlisted",
    "private": "private",
}

STATUS_PUBLISHED = "published"
STATUS_PROCESSING = "processing"
STATUS_FAILED = "failed"


def resolve_access_token(
    credentials: dict,
    *,
    token_url: str = OAUTH_TOKEN_URL,
    transport: "httpx.BaseTransport | None" = None,
    timeout_sec: float = 30.0,
) -> str:
    """Return a usable access token: direct token or OAuth2 refresh_token flow.

    client_id/client_secret fall back to settings (youtube_client_id/secret).
    Raises PlatformError('missing_credentials' | 'token_refresh_failed').
    Shared with the metrics adapter — single Google-auth code path.
    """
    credentials = credentials or {}
    access_token = credentials.get("access_token")
    if access_token:
        return str(access_token)

    refresh_token = credentials.get("refresh_token")
    if not refresh_token:
        raise PlatformError(
            "missing_credentials",
            "PlatformAccount credentials need access_token or refresh_token",
        )
    settings = get_settings()
    client_id = credentials.get("client_id") or settings.youtube_client_id
    client_secret = credentials.get("client_secret") or settings.youtube_client_secret
    if not client_id or not client_secret:
        raise PlatformError(
            "missing_credentials",
            "refresh_token flow needs client_id/client_secret (credentials or settings)",
        )

    try:
        with httpx.Client(timeout=timeout_sec, transport=transport) as client:
            response = client.post(
                token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except httpx.HTTPError as exc:
        raise PlatformError("network_error", f"Google token endpoint unreachable: {exc}") from exc
    if response.status_code != 200:
        raise PlatformError(
            "token_refresh_failed",
            f"Google token endpoint returned HTTP {response.status_code}",
        )
    try:
        token = response.json().get("access_token")
    except ValueError:
        token = None
    if not token:
        raise PlatformError("token_refresh_failed", "Google token response has no access_token")
    return str(token)


@register_publisher
class YouTubePublisher:
    platform = "youtube"

    def __init__(
        self,
        api_base_url: str = API_BASE_URL,
        upload_base_url: str = UPLOAD_BASE_URL,
        token_url: str = OAUTH_TOKEN_URL,
        timeout_sec: float = 300.0,  # video upload of tens of MB on slow uplink
        transport: "httpx.BaseTransport | None" = None,  # test injection point
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.upload_base_url = upload_base_url.rstrip("/")
        self.token_url = token_url
        self.timeout_sec = timeout_sec
        self.transport = transport

    # --- public API ---

    def publish(self, request: PublishRequest, credentials: dict) -> PublishResult:
        token = resolve_access_token(credentials, token_url=self.token_url,
                                     transport=self.transport)
        metadata = self._build_metadata(request)

        size = Path(request.video_path).stat().st_size
        with httpx.Client(timeout=self.timeout_sec, transport=self.transport) as client:
            # step 1: open a resumable session with the metadata
            init_response = client.post(
                f"{self.upload_base_url}/upload/youtube/v3/videos",
                params={"uploadType": "resumable", "part": "snippet,status"},
                json=metadata,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Upload-Content-Type": "video/mp4",
                    "X-Upload-Content-Length": str(size),
                },
            )
            if init_response.status_code != 200:
                raise PlatformError(
                    "upload_init_failed",
                    f"videos.insert init failed: HTTP {init_response.status_code} "
                    f"{self._google_error(init_response)}",
                )
            session_url = init_response.headers.get("location")
            if not session_url:
                raise PlatformError(
                    "upload_init_failed", "no resumable session URL in response"
                )

            # step 2: upload the bytes in a single PUT on the session
            video_bytes = Path(request.video_path).read_bytes()
            upload_response = client.put(
                session_url,
                content=video_bytes,
                headers={"Content-Type": "video/mp4"},
            )

        if upload_response.status_code not in (200, 201):
            raise PlatformError(
                "upload_failed",
                f"video upload failed: HTTP {upload_response.status_code} "
                f"{self._google_error(upload_response)}",
            )
        try:
            body = upload_response.json()
        except ValueError:
            raise PlatformError("invalid_response", "non-JSON upload response") from None
        video_id = body.get("id")
        if not video_id:
            raise PlatformError("invalid_response", "upload response has no video id")

        privacy = (body.get("status") or {}).get("privacyStatus") or metadata["status"]["privacyStatus"]
        logger.info("youtube upload ok: video_id=%s privacy=%s", video_id, privacy)
        return PublishResult(
            external_post_id=str(video_id),
            status=STATUS_PUBLISHED,
            raw={"video_id": str(video_id), "privacyStatus": privacy,
                 "uploadStatus": (body.get("status") or {}).get("uploadStatus")},
        )

    def check_status(self, external_post_id: str, credentials: dict) -> str:
        token = resolve_access_token(credentials, token_url=self.token_url,
                                     transport=self.transport)
        with httpx.Client(timeout=30, transport=self.transport) as client:
            response = client.get(
                f"{self.api_base_url}/youtube/v3/videos",
                params={"part": "status", "id": external_post_id},
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code != 200:
            raise PlatformError(
                "status_check_failed",
                f"videos.list failed: HTTP {response.status_code} {self._google_error(response)}",
            )
        items = (response.json() or {}).get("items") or []
        if not items:
            raise PlatformError("video_not_found", f"no youtube video {external_post_id}")
        upload_status = (items[0].get("status") or {}).get("uploadStatus")
        if upload_status in ("uploaded", "processed"):
            return STATUS_PUBLISHED
        if upload_status in ("rejected", "failed", "deleted"):
            return STATUS_FAILED
        return STATUS_PROCESSING

    # --- internals ---

    def _build_metadata(self, request: PublishRequest) -> dict:
        title = (request.title or "")[:TITLE_MAX_CHARS].strip() or "Untitled clip"
        description = (request.description or "")[:DESCRIPTION_MAX_CHARS]
        tags = [t for t in request.tags if t][: TAGS_TOTAL_MAX_CHARS // 2]  # practical cap
        while tags and sum(len(t) + 1 for t in tags) > TAGS_TOTAL_MAX_CHARS:
            tags.pop()
        privacy = PRIVACY_MAP.get(request.privacy)
        if privacy is None:
            raise PlatformError(
                "invalid_privacy", f"unsupported privacy '{request.privacy}'"
            )
        return {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": DEFAULT_CATEGORY_ID,
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,  # user-generated clips; required field
            },
        }

    @staticmethod
    def _google_error(response: httpx.Response) -> str:
        """Extract error reason from a Google JSON error body (secret-free)."""
        try:
            error = (response.json() or {}).get("error") or {}
            errors = error.get("errors") or [{}]
            reason = errors[0].get("reason") or error.get("status") or ""
            message = (errors[0].get("message") or error.get("message") or "")[:200]
            return f"{reason}: {message}".strip(": ")
        except ValueError:
            return ""
