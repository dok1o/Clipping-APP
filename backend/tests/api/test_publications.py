"""Publications API contract tests with a fake publisher (no network)."""
import io
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.fakes import FakePublisher


@pytest.fixture
def rendered_clip(client, monkeypatch):
    """Video + clip + rendered asset (render faked), returns (clip_id, asset_id)."""
    from app.services.render import render_service

    monkeypatch.setattr(
        render_service, "render_vertical",
        lambda s, d, **k: __import__("pathlib").Path(d).write_bytes(b"rendered"),
    )
    video = client.post(
        "/api/v1/videos",
        files={"file": ("v.mp4", io.BytesIO(b"\x00\x00\x00\x18ftypmp42data"), "video/mp4")},
    ).json()
    clip = client.post(
        f"/api/v1/videos/{video['id']}/clips/manual",
        json={"title": "moment", "start_sec": 1.0, "end_sec": 10.0},
    ).json()
    job = client.post(f"/api/v1/clips/{clip['id']}/render").json()
    asset_id = client.get(f"/api/v1/jobs/{job['id']}").json()["result"]["asset_id"]
    return clip["id"], asset_id


@pytest.fixture
def tiktok_account(client):
    return client.post(
        "/api/v1/platform-accounts",
        json={
            "platform": "tiktok",
            "external_account_id": "user-123",
            "display_name": "Test Creator",
            "credentials": {"access_token": "act.secret-token-value"},
            "scopes": ["video.publish"],
        },
    ).json()


@pytest.fixture
def fake_publisher(monkeypatch):
    publisher = FakePublisher()
    from app.services.publish import publish_service

    monkeypatch.setattr(publish_service, "get_publisher", lambda platform, **kw: publisher)
    return publisher


def _publish(client, clip_id, account_id, **overrides):
    payload = {
        "clip_id": clip_id,
        "platform": "tiktok",
        "platform_account_id": account_id,
        "title": "My clip #fyp",
        "description": "desc",
        "privacy": "public",
        "scheduled_at": None,
    }
    payload.update(overrides)
    payload = {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in payload.items()}
    return client.post("/api/v1/publications/manual", json=payload)


def test_manual_publish_201_published(client, rendered_clip, tiktok_account, fake_publisher, db) -> None:
    clip_id, _asset_id = rendered_clip
    response = _publish(client, clip_id, tiktok_account["id"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "published"
    assert body["external_post_id"] == "fake-post-1"
    assert body["platform"] == "tiktok"
    assert body["published_at"] is not None
    assert body["metadata"]["title"] == "My clip #fyp"
    assert fake_publisher.calls[0].title == "My clip #fyp"

    # credentials never leak: encrypted in DB, masked in API
    from app.models.platform_account import PlatformAccount

    account = db.get(PlatformAccount, uuid.UUID(tiktok_account["id"]))
    assert "act.secret-token-value" not in account.credentials_encrypted
    assert tiktok_account["credentials"] == "***"


def test_duplicate_publish_409(client, rendered_clip, tiktok_account, fake_publisher) -> None:
    clip_id, _ = rendered_clip
    assert _publish(client, clip_id, tiktok_account["id"]).status_code == 201
    duplicate = _publish(client, clip_id, tiktok_account["id"])
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "duplicate_publication"


def test_platform_error_502_and_publication_failed(client, rendered_clip, tiktok_account, monkeypatch) -> None:
    from app.services.publish import publish_service
    from app.services.publish.base import PlatformError

    monkeypatch.setattr(
        publish_service, "get_publisher",
        lambda platform, **kw: FakePublisher(
            fail_with=PlatformError("unaudited_client_can_only_post_to_private_accounts", "blocked")
        ),
    )
    clip_id, _ = rendered_clip
    response = _publish(client, clip_id, tiktok_account["id"])
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "platform_error"

    listing = client.get("/api/v1/publications", params={"clip_id": clip_id}).json()
    assert listing["total"] == 1
    failed = listing["items"][0]
    assert failed["status"] == "failed"
    assert "unaudited_client" in failed["last_error"]

    # retry with a different title => allowed (failed publication does not block)
    monkeypatch.setattr(publish_service, "get_publisher", lambda platform, **kw: FakePublisher())
    ok = _publish(client, clip_id, tiktok_account["id"], title="Another title")
    assert ok.status_code == 201


def test_scheduled_publication_not_published_now(client, rendered_clip, tiktok_account, fake_publisher) -> None:
    clip_id, _ = rendered_clip
    when = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    response = _publish(client, clip_id, tiktok_account["id"], scheduled_at=when)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "scheduled"
    assert body["published_at"] is None
    assert fake_publisher.calls == []  # Stage 5 worker will handle the schedule


def test_publish_asset_not_found(client, rendered_clip, tiktok_account, fake_publisher, db) -> None:
    # clip without rendered asset
    video = client.post(
        "/api/v1/videos",
        files={"file": ("v2.mp4", io.BytesIO(b"data"), "video/mp4")},
    ).json()
    clip = client.post(
        f"/api/v1/videos/{video['id']}/clips/manual",
        json={"title": "no render", "start_sec": 0.0, "end_sec": 10.0},
    ).json()
    response = _publish(client, clip["id"], tiktok_account["id"])
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "asset_not_found"


def test_publish_clip_not_found(client, tiktok_account, fake_publisher) -> None:
    response = _publish(client, uuid.uuid4(), tiktok_account["id"])
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "clip_not_found"


def test_publish_account_not_found(client, rendered_clip, fake_publisher) -> None:
    clip_id, _ = rendered_clip
    response = _publish(client, clip_id, uuid.uuid4())
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "account_not_found"


def test_publish_platform_mismatch_422(client, rendered_clip, fake_publisher) -> None:
    clip_id, _ = rendered_clip
    youtube_account = client.post(
        "/api/v1/platform-accounts",
        json={"platform": "youtube", "external_account_id": "chan-1", "credentials": {"x": "y"}},
    ).json()
    response = _publish(client, clip_id, youtube_account["id"])
    assert response.status_code == 422


def test_get_publication_and_list(client, rendered_clip, tiktok_account, fake_publisher) -> None:
    clip_id, _ = rendered_clip
    created = _publish(client, clip_id, tiktok_account["id"]).json()
    got = client.get(f"/api/v1/publications/{created['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == created["id"]
    assert client.get(f"/api/v1/publications/{uuid.uuid4()}").status_code == 404
    page = client.get("/api/v1/publications", params={"platform": "tiktok"}).json()
    assert page["total"] == 1
