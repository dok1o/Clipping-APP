"""YouTube Data API v3 publisher (resumable upload) — official protocol, mocked HTTP."""
import io
import json as _json
from pathlib import Path

import httpx
import pytest

from app.services.publish.base import PlatformError, PublishRequest
from app.services.publish.youtube import PRIVACY_MAP, YouTubePublisher

SESSION_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=abc123"


def _write_video(tmp_path: Path) -> Path:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"data" * 100)
    return video


def _transport(tmp_path: Path, *, init_status=200, upload_status=200, refresh=True):
    """YouTube official flow mock: [token refresh] -> init (Location) -> PUT bytes."""
    state = {"refreshed": 0, "inits": 0, "uploads": 0, "init_body": None, "upload_body": None}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            state["refreshed"] += 1
            assert "grant_type=refresh_token" in request.content.decode()
            return httpx.Response(200, json={"access_token": "AT-REFRESHED", "expires_in": 3600})
        if request.method == "POST" and "/upload/youtube/v3/videos" in str(request.url):
            state["inits"] += 1
            state["init_body"] = _json.loads(request.content)
            assert request.url.params.get("uploadType") == "resumable"
            assert request.url.params.get("part") == "snippet,status"
            if init_status != 200:
                return httpx.Response(init_status, json={
                    "error": {"errors": [{"reason": "quotaExceeded", "message": "Video Uploads per day"}]}
                })
            return httpx.Response(200, headers={"Location": SESSION_URL})
        if request.method == "PUT" and "upload_id=abc123" in str(request.url):
            state["uploads"] += 1
            state["upload_body"] = request.content
            if upload_status != 200:
                return httpx.Response(upload_status, json={
                    "error": {"errors": [{"reason": "forbidden", "message": "The request is not properly authorized"}]}
                })
            return httpx.Response(200, json={
                "id": "dQw4w9WgXcQ",
                "status": {"uploadStatus": "uploaded", "privacyStatus": "public"},
            })
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    return httpx.MockTransport(handler), state


def test_publish_resumable_two_steps(tmp_path: Path) -> None:
    transport, state = _transport(tmp_path)
    publisher = YouTubePublisher(transport=transport)
    result = publisher.publish(
        PublishRequest(video_path=str(_write_video(tmp_path)), title="My clip",
                       description="desc", privacy="public", tags=["shorts"]),
        credentials={"access_token": "tok"},
    )
    assert result.external_post_id == "dQw4w9WgXcQ"
    assert result.status == "published"
    assert result.raw["privacyStatus"] == "public"
    # init metadata per official guide
    snippet = state["init_body"]["snippet"]
    assert snippet["title"] == "My clip" and snippet["categoryId"] == "22"
    assert state["init_body"]["status"]["privacyStatus"] == "public"
    assert state["init_body"]["status"]["selfDeclaredMadeForKids"] is False
    # the actual video bytes went to the session URL
    assert state["upload_body"] == (tmp_path / "clip.mp4").read_bytes()
    assert state["refreshed"] == 0  # direct access_token: no refresh call


def test_publish_refresh_token_flow(tmp_path: Path, monkeypatch) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "youtube_client_id", "cid")
    monkeypatch.setattr(settings, "youtube_client_secret", "csecret")
    transport, state = _transport(tmp_path)
    publisher = YouTubePublisher(transport=transport)
    result = publisher.publish(
        PublishRequest(video_path=str(_write_video(tmp_path)), title="t", privacy="unlisted"),
        credentials={"refresh_token": "rt"},
    )
    assert result.external_post_id == "dQw4w9WgXcQ"
    assert state["refreshed"] == 1
    assert state["init_body"]["status"]["privacyStatus"] == "unlisted"


def test_missing_credentials(tmp_path: Path) -> None:
    publisher = YouTubePublisher(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(PlatformError) as e:
        publisher.publish(
            PublishRequest(video_path=str(_write_video(tmp_path)), title="t"),
            credentials={},
        )
    assert e.value.code == "missing_credentials"


def test_title_truncated_and_tags_capped(tmp_path: Path) -> None:
    transport, state = _transport(tmp_path)
    publisher = YouTubePublisher(transport=transport)
    publisher.publish(
        PublishRequest(video_path=str(_write_video(tmp_path)),
                       title="x" * 300, privacy="private",
                       tags=["tag%d" % i for i in range(50)]),
        credentials={"access_token": "tok"},
    )
    assert len(state["init_body"]["snippet"]["title"]) == 100
    assert sum(len(t) + 1 for t in state["init_body"]["snippet"]["tags"]) <= 500


def test_invalid_privacy_rejected(tmp_path: Path) -> None:
    publisher = YouTubePublisher(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    with pytest.raises(PlatformError) as e:
        publisher.publish(
            PublishRequest(video_path=str(_write_video(tmp_path)), title="t", privacy="friends"),
            credentials={"access_token": "tok"},
        )
    assert e.value.code == "invalid_privacy"


def test_init_error_surfaces_google_reason(tmp_path: Path) -> None:
    transport, _ = _transport(tmp_path, init_status=403)
    publisher = YouTubePublisher(transport=transport)
    with pytest.raises(PlatformError) as e:
        publisher.publish(
            PublishRequest(video_path=str(_write_video(tmp_path)), title="t"),
            credentials={"access_token": "tok"},
        )
    assert e.value.code == "upload_init_failed"
    assert "quotaExceeded" in e.value.message


def test_upload_error_surfaces_google_reason(tmp_path: Path) -> None:
    transport, _ = _transport(tmp_path, upload_status=403)
    publisher = YouTubePublisher(transport=transport)
    with pytest.raises(PlatformError) as e:
        publisher.publish(
            PublishRequest(video_path=str(_write_video(tmp_path)), title="t"),
            credentials={"access_token": "tok"},
        )
    assert e.value.code == "upload_failed"
    assert "forbidden" in e.value.message


def test_check_status_mapping() -> None:
    def make(upload_status: str | None, items=True):
        body = {"items": ([{"status": {"uploadStatus": upload_status}}] if items else [])}
        return httpx.MockTransport(
            lambda r: httpx.Response(200, json=body)
        )

    publisher = YouTubePublisher(transport=make("uploaded"))
    assert publisher.check_status("v", {"access_token": "t"}) == "published"
    publisher = YouTubePublisher(transport=make("processed"))
    assert publisher.check_status("v", {"access_token": "t"}) == "published"
    publisher = YouTubePublisher(transport=make("rejected"))
    assert publisher.check_status("v", {"access_token": "t"}) == "failed"
    publisher = YouTubePublisher(transport=make(None))
    assert publisher.check_status("v", {"access_token": "t"}) == "processing"
    publisher = YouTubePublisher(transport=make("x", items=False))
    with pytest.raises(PlatformError) as e:
        publisher.check_status("v", {"access_token": "t"})
    assert e.value.code == "video_not_found"


def test_privacy_map_native() -> None:
    assert PRIVACY_MAP == {"public": "public", "unlisted": "unlisted", "private": "private"}


def test_full_youtube_publication_flow_via_service(client, monkeypatch, tmp_path) -> None:
    """End-to-end: render -> youtube account -> manual publish via the REAL
    YouTubePublisher over mocked official HTTP -> Publication published."""
    from app.core.config import get_settings
    from app.services.render import render_service
    from app.services.publish import publish_service

    monkeypatch.setattr(get_settings(), "youtube_client_id", "cid")
    monkeypatch.setattr(get_settings(), "youtube_client_secret", "csecret")
    monkeypatch.setattr(
        render_service, "render_vertical",
        lambda s, d, **k: Path(d).write_bytes(b"rendered"),
    )
    transport, state = _transport(tmp_path)
    monkeypatch.setattr(
        publish_service, "get_publisher",
        lambda platform, **kw: YouTubePublisher(transport=transport),
    )

    video = client.post(
        "/api/v1/videos",
        files={"file": ("v.mp4", io.BytesIO(b"\x00\x00\x00\x18ftypmp42data"), "video/mp4")},
    ).json()
    clip = client.post(
        f"/api/v1/videos/{video['id']}/clips/manual",
        json={"title": "yt clip", "start_sec": 0.0, "end_sec": 10.0},
    ).json()
    job = client.post(f"/api/v1/clips/{clip['id']}/render").json()
    assert client.get(f"/api/v1/jobs/{job['id']}").json()["status"] == "succeeded"

    account = client.post(
        "/api/v1/platform-accounts",
        json={"platform": "youtube", "external_account_id": "channel-1",
              "credentials": {"refresh_token": "rt"}},
    ).json()

    publication = client.post(
        "/api/v1/publications/manual",
        json={"clip_id": clip["id"], "platform": "youtube",
              "platform_account_id": account["id"],
              "title": "YouTube Short via official API", "privacy": "public"},
    ).json()
    assert publication["status"] == "published", publication
    assert publication["external_post_id"] == "dQw4w9WgXcQ"
    assert state["uploads"] == 1
