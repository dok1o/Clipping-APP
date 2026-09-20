"""TikTok adapter unit tests against httpx.MockTransport (no network)."""
import json

import httpx
import pytest

from app.services.publish.base import PlatformError, PublishRequest
from app.services.publish.tiktok import PRIVACY_MAP, TikTokPublisher


def _client_transport(responses: list[httpx.Response]):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if responses:
            return responses.pop(0)
        return httpx.Response(200, json={"error": {"code": "ok", "message": ""}})

    return httpx.MockTransport(handler), calls


def _ok_init() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "data": {"publish_id": "v_pub_file~v2-1.abc", "upload_url": "https://upload.example/u?tok=1"},
            "error": {"code": "ok", "message": ""},
        },
    )


def test_publish_full_flow_happy_path(tmp_path) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"0" * 1000)
    responses = [
        _ok_init(),
        httpx.Response(204),
        httpx.Response(200, json={"data": {"status": "PUBLISH_COMPLETE"}, "error": {"code": "ok"}}),
    ]
    transport, calls = _client_transport(responses)
    publisher = TikTokPublisher(base_url="https://api.example", transport=transport, poll_delay_sec=0)

    result = publisher.publish(
        PublishRequest(video_path=str(video), title="hi #fyp", privacy="public"),
        {"access_token": "tok"},
    )
    assert result.external_post_id == "v_pub_file~v2-1.abc"
    assert result.status == "published"

    init_call = calls[0]
    assert init_call.url.path == "/v2/post/publish/video/init/"
    assert init_call.headers["Authorization"] == "Bearer tok"
    body = json.loads(init_call.content)
    assert body["post_info"]["privacy_level"] == "PUBLIC_TO_EVERYONE"
    assert body["post_info"]["title"] == "hi #fyp"
    assert body["source_info"]["source"] == "FILE_UPLOAD"
    assert body["source_info"]["video_size"] == 1000
    assert body["source_info"]["total_chunk_count"] == 1

    upload_call = calls[1]
    assert upload_call.method == "PUT"
    assert upload_call.headers["Content-Range"] == "bytes 0-999/1000"
    assert upload_call.headers["Content-Type"] == "video/mp4"

    status_call = calls[2]
    assert status_call.url.path == "/v2/post/publish/status/fetch/"
    assert json.loads(status_call.content) == {"publish_id": "v_pub_file~v2-1.abc"}


def test_publish_failed_status_raises(tmp_path) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x" * 10)
    responses = [
        _ok_init(),
        httpx.Response(204),
        httpx.Response(200, json={"data": {"status": "FAILED", "fail_reason": "Video corrupted"},
                                  "error": {"code": "ok"}}),
    ]
    transport, _ = _client_transport(responses)
    publisher = TikTokPublisher(base_url="https://api.example", transport=transport, poll_delay_sec=0)
    with pytest.raises(PlatformError) as e:
        publisher.publish(PublishRequest(video_path=str(video), title="t"), {"access_token": "tok"})
    assert e.value.code == "publish_failed"


def test_api_error_propagates_code(tmp_path) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x" * 10)
    transport, _ = _client_transport([
        httpx.Response(403, json={"error": {"code": "unaudited_client_can_only_post_to_private_accounts",
                                            "message": "blocked"}})
    ])
    publisher = TikTokPublisher(base_url="https://api.example", transport=transport, poll_delay_sec=0)
    with pytest.raises(PlatformError) as e:
        publisher.publish(PublishRequest(video_path=str(video), title="t"), {"access_token": "tok"})
    assert e.value.code == "unaudited_client_can_only_post_to_private_accounts"


def test_missing_token(tmp_path) -> None:
    publisher = TikTokPublisher(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    with pytest.raises(PlatformError) as e:
        publisher.publish(PublishRequest(video_path="/tmp/x.mp4", title="t"), {})
    assert e.value.code == "missing_credentials"


def test_title_building_with_tags_and_limit() -> None:
    title = TikTokPublisher._build_title(
        PublishRequest(video_path="x", title="смотри", description="описание", tags=["fyp", "клип"])
    )
    assert "#fyp" in title and "#клип" in title
    long = TikTokPublisher._build_title(PublishRequest(video_path="x", title="t" * 5000))
    assert len(long) == 2200


def test_privacy_map_covers_unified_enum() -> None:
    assert set(PRIVACY_MAP) == {"public", "unlisted", "private"}
    assert PRIVACY_MAP["private"] == "SELF_ONLY"


def test_check_status_mapping(tmp_path) -> None:
    transport, _ = _client_transport([
        httpx.Response(200, json={"data": {"status": "PUBLISH_COMPLETE"}, "error": {"code": "ok"}})
    ])
    publisher = TikTokPublisher(base_url="https://api.example", transport=transport, poll_delay_sec=0)
    assert publisher.check_status("pid", {"access_token": "tok"}) == "published"
