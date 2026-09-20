"""Metrics: TikTok adapter (mock transport) + service flow with a fake adapter."""
import io
import uuid

import httpx
import pytest


def _published_publication(client, monkeypatch):
    """Video -> clip -> render -> account -> published publication (fake publisher)."""
    from pathlib import Path

    from app.services.render import render_service
    from tests.fakes import FakePublisher

    monkeypatch.setattr(
        render_service, "render_vertical",
        lambda s, d, **k: Path(d).write_bytes(b"rendered"),
    )
    from app.services.publish import publish_service

    publisher = FakePublisher(external_post_id="7312345678901234567")
    monkeypatch.setattr(publish_service, "get_publisher", lambda platform, **kw: publisher)

    video = client.post(
        "/api/v1/videos",
        files={"file": ("v.mp4", io.BytesIO(b"\x00\x00\x00\x18ftypmp42data"), "video/mp4")},
    ).json()
    clip = client.post(
        f"/api/v1/videos/{video['id']}/clips/manual",
        json={"title": "metrics clip", "start_sec": 0.0, "end_sec": 10.0},
    ).json()
    job = client.post(f"/api/v1/clips/{clip['id']}/render").json()
    asset_id = client.get(f"/api/v1/jobs/{job['id']}").json()["result"]["asset_id"]

    account = client.post(
        "/api/v1/platform-accounts",
        json={"platform": "tiktok", "external_account_id": "u1",
              "credentials": {"access_token": "tok"}},
    ).json()
    publication = client.post(
        "/api/v1/publications/manual",
        json={"clip_id": clip["id"], "platform": "tiktok", "platform_account_id": account["id"],
              "title": "metrics test", "privacy": "private"},
    ).json()
    assert publication["status"] == "published"
    return publication, asset_id


def test_tiktok_adapter_parses_statistics() -> None:
    from app.services.analytics.metrics_service import TikTokMetricsAdapter

    def handler(request: httpx.Request) -> httpx.Response:
        assert "fields=id,view_count" in str(request.url)
        assert request.url.path == "/v2/video/query/"
        return httpx.Response(200, json={
            "data": {"videos": [{
                "id": "7312345678901234567", "view_count": 1500,
                "like_count": 42, "comment_count": 7, "share_count": 3,
            }]},
            "error": {"code": "ok"},
        })

    adapter = TikTokMetricsAdapter(base_url="https://api.test", transport=httpx.MockTransport(handler))
    data = adapter.fetch("7312345678901234567", {"access_token": "tok"})
    assert data["views"] == 1500 and data["likes"] == 42
    assert data["comments"] == 7 and data["shares"] == 3
    assert data["raw"]["data"]["videos"][0]["id"] == "7312345678901234567"


def test_tiktok_adapter_error_code() -> None:
    from app.services.analytics.metrics_service import MetricsError, TikTokMetricsAdapter

    transport = httpx.MockTransport(
        lambda r: httpx.Response(403, json={"error": {"code": "access_token_invalid", "message": "bad"}})
    )
    adapter = TikTokMetricsAdapter(base_url="https://api.test", transport=transport)
    with pytest.raises(MetricsError) as e:
        adapter.fetch("x", {"access_token": "tok"})
    assert e.value.code == "access_token_invalid"


def test_tiktok_adapter_video_not_found() -> None:
    from app.services.analytics.metrics_service import MetricsError, TikTokMetricsAdapter

    transport = httpx.MockTransport(
        lambda r: httpx.Response(200, json={"data": {"videos": []}, "error": {"code": "ok"}})
    )
    adapter = TikTokMetricsAdapter(base_url="https://api.test", transport=transport)
    with pytest.raises(MetricsError) as e:
        adapter.fetch("missing", {"access_token": "tok"})
    assert e.value.code == "video_not_found"


def test_sync_metrics_flow_with_fake_adapter(client, monkeypatch, _published_publication=None) -> None:
    # build a published publication via the shared helper
    from tests.unit.test_metrics import _published_publication as helper  # noqa: F401

    pub, _asset = helper(client, monkeypatch)

    from app.services.analytics import metrics_service

    class FakeAdapter:
        platform = "tiktok"

        def fetch(self, external_post_id, credentials):
            return {"views": 100, "likes": 5, "comments": 2, "shares": 1,
                    "raw": {"official": "response", "video_id": external_post_id}}

    monkeypatch.setattr(metrics_service, "get_metrics_adapter", lambda platform, **kw: FakeAdapter())

    response = client.post(f"/api/v1/publications/{pub['id']}/sync-metrics")
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    job = client.get(f"/api/v1/jobs/{job_id}").json()
    assert job["status"] == "succeeded"
    assert job["result"]["views"] == 100

    metrics = client.get(f"/api/v1/publications/{pub['id']}/metrics").json()
    assert metrics["total"] == 1
    metric = metrics["items"][0]
    assert metric["views"] == 100 and metric["likes"] == 5
    assert metric["raw"]["official"] == "response"  # raw preserved
    assert metric["captured_at"].endswith("Z")


def test_sync_requires_published(client, monkeypatch) -> None:
    video = client.post(
        "/api/v1/videos",
        files={"file": ("v.mp4", io.BytesIO(b"data"), "video/mp4")},
    ).json()
    clip = client.post(
        f"/api/v1/videos/{video['id']}/clips/manual",
        json={"title": "no render", "start_sec": 0.0, "end_sec": 10.0},
    ).json()
    response = client.post(f"/api/v1/publications/{uuid.uuid4()}/sync-metrics")
    assert response.status_code == 404
    from tests.unit.test_metrics import _published_publication as helper

    pub, _ = helper(client, monkeypatch)
    # simulate non-published state
    from app.db import session as db_session
    from app.models.publication import Publication, PublicationStatus

    db = db_session.session_factory()
    row = db.get(Publication, uuid.UUID(pub["id"]))
    row.status = PublicationStatus.FAILED
    db.commit()
    db.close()
    denied = client.post(f"/api/v1/publications/{pub['id']}/sync-metrics")
    assert denied.status_code == 409
    assert denied.json()["detail"]["code"] == "publication_not_published"


def test_sync_failure_records_job_error(client, monkeypatch) -> None:
    from tests.unit.test_metrics import _published_publication as helper

    pub, _ = helper(client, monkeypatch)
    from app.services.analytics import metrics_service
    from app.services.analytics.metrics_service import MetricsError

    class Broken:
        platform = "tiktok"

        def fetch(self, *a, **k):
            raise MetricsError("network_error", "tiktok down")

    monkeypatch.setattr(metrics_service, "get_metrics_adapter", lambda platform, **kw: Broken())
    response = client.post(f"/api/v1/publications/{pub['id']}/sync-metrics")
    assert response.status_code == 202
    job = client.get(f"/api/v1/jobs/{response.json()['job_id']}").json()
    assert job["status"] == "failed"
    assert "network_error" in job["error_message"]
    assert client.get(f"/api/v1/publications/{pub['id']}/metrics").json()["total"] == 0


def test_youtube_adapter_parses_statistics() -> None:
    from app.services.analytics.metrics_service import YouTubeMetricsAdapter

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("part") == "statistics"
        assert request.url.params.get("id") == "dQw4w9WgXcQ"
        return httpx.Response(200, json={
            "items": [{"id": "dQw4w9WgXcQ", "statistics": {
                "viewCount": "1543", "likeCount": "99", "commentCount": "12", "favoriteCount": "0",
            }}],
        })

    adapter = YouTubeMetricsAdapter(base_url="https://api.test", transport=httpx.MockTransport(handler))
    data = adapter.fetch("dQw4w9WgXcQ", {"access_token": "tok"})
    assert data["views"] == 1543 and data["likes"] == 99 and data["comments"] == 12
    assert data["shares"] is None  # YouTube official API has no share counter
    assert data["raw"]["items"][0]["statistics"]["viewCount"] == "1543"


def test_youtube_adapter_not_found() -> None:
    from app.services.analytics.metrics_service import MetricsError, YouTubeMetricsAdapter

    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"items": []}))
    adapter = YouTubeMetricsAdapter(base_url="https://api.test", transport=transport)
    with pytest.raises(MetricsError) as e:
        adapter.fetch("gone", {"access_token": "tok"})
    assert e.value.code == "video_not_found"


def test_youtube_adapter_refreshes_token() -> None:
    from app.services.analytics.metrics_service import YouTubeMetricsAdapter

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "AT"})
        assert request.headers.get("authorization") == "Bearer AT"
        return httpx.Response(200, json={"items": [{"statistics": {"viewCount": "5"}}]})

    adapter = YouTubeMetricsAdapter(base_url="https://www.googleapis.com",
                                    transport=httpx.MockTransport(handler))
    data = adapter.fetch("v1", {"refresh_token": "rt", "client_id": "cid", "client_secret": "cs"})
    assert data["views"] == 5
