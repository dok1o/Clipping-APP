"""Autopublish: due -> published, rate limits, duplicate protection (spec §21)."""
import io
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.fakes import FakePublisher


@pytest.fixture
def rendered_clip(client, monkeypatch):
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
        json={"title": "scheduled clip", "start_sec": 1.0, "end_sec": 10.0},
    ).json()
    job = client.post(f"/api/v1/clips/{clip['id']}/render").json()
    asset_id = client.get(f"/api/v1/jobs/{job['id']}").json()["result"]["asset_id"]
    return clip["id"], asset_id


@pytest.fixture
def account(client):
    return client.post(
        "/api/v1/platform-accounts",
        json={"platform": "tiktok", "external_account_id": "u1",
              "credentials": {"access_token": "tok"}},
    ).json()


@pytest.fixture
def publisher(monkeypatch):
    pub = FakePublisher()
    from app.services.publish import publish_service

    monkeypatch.setattr(publish_service, "get_publisher", lambda platform, **kw: pub)
    return pub


def _schedule(client, clip_id, account_id, title="Scheduled #fyp", minutes_ago=5):
    when = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
    return client.post(
        "/api/v1/publications/manual",
        json={
            "clip_id": clip_id, "platform": "tiktok", "platform_account_id": account_id,
            "title": title, "privacy": "private", "scheduled_at": when,
        },
    )


def _storage():
    from app.core.config import get_settings
    from app.infra.s3 import S3Storage

    return S3Storage.from_settings(get_settings())


def _process(client, monkeypatch=None):
    from app.db import session as db_session
    from app.services.publish import publish_service

    db = db_session.session_factory()
    try:
        return publish_service.process_due_publications(db, _storage())
    finally:
        db.close()


def test_due_scheduled_published_by_worker(client, rendered_clip, account, publisher) -> None:
    clip_id, _ = rendered_clip
    response = _schedule(client, clip_id, account["id"])
    assert response.status_code == 201
    assert response.json()["status"] == "scheduled"

    results = _process(client)
    assert results["published"] == 1
    listing = client.get("/api/v1/publications").json()
    assert listing["items"][0]["status"] == "published"
    assert listing["items"][0]["external_post_id"] == "fake-post-1"
    assert len(publisher.calls) == 1


def test_double_run_single_external_id(client, rendered_clip, account, publisher) -> None:
    """Spec §21: двойной запуск → 1 external_post_id (guard + idempotent no-op)."""
    clip_id, _ = rendered_clip
    _schedule(client, clip_id, account["id"])
    first = _process(client)
    second = _process(client)  # nothing due anymore
    assert first["published"] == 1
    assert second == {"published": 0, "failed": 0, "rescheduled": 0, "skipped": 0}
    assert len(publisher.calls) == 1  # uploaded exactly once

    # direct re-execution of the same publication is a no-op
    from app.db import session as db_session
    from app.models.publication import Publication
    from app.services.publish import publish_service

    db = db_session.session_factory()
    pub = db.scalars(__import__("sqlalchemy", fromlist=["select"]).select(Publication)).first()
    finished = publish_service.execute_scheduled_publication(db, _storage(), pub.id)
    assert finished.status == "published"
    assert len(publisher.calls) == 1  # external_post_id guard prevented re-upload
    db.close()


def test_rate_limit_daily_reschedules(client, rendered_clip, account, publisher, monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "tiktok_daily_limit", 0)  # limit reached
    clip_id, _ = rendered_clip
    _schedule(client, clip_id, account["id"])
    results = _process(client)
    assert results["rescheduled"] == 1
    assert results["published"] == 0
    listing = client.get("/api/v1/publications").json()
    assert listing["items"][0]["status"] == "scheduled"  # moved forward, not lost
    assert publisher.calls == []


def test_min_interval_reschedules(client, rendered_clip, account, publisher, monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "publish_min_interval_sec", 3600)
    clip_id, _ = rendered_clip
    _schedule(client, clip_id, account["id"], title="first")
    assert _process(client)["published"] == 1

    # a second clip scheduled due immediately -> must wait for the interval
    # (same clip+platform would be blocked by the partial unique on purpose)
    video = client.get("/api/v1/videos").json()["items"][0]
    clip2 = client.post(
        f"/api/v1/videos/{video['id']}/clips/manual",
        json={"title": "second clip", "start_sec": 5.0, "end_sec": 20.0},
    ).json()
    # second clip needs its own rendered asset
    from pathlib import Path

    from app.services.render import render_service

    original = render_service.render_vertical
    render_service.render_vertical = lambda s, d, **k: Path(d).write_bytes(b"r2")
    job = client.post(f"/api/v1/clips/{clip2['id']}/render").json()
    render_service.render_vertical = original
    assert client.get(f"/api/v1/jobs/{job['id']}").json()["status"] == "succeeded"

    _schedule(client, clip2["id"], account["id"], title="second")
    results = _process(client)
    assert results["rescheduled"] == 1
    assert results["published"] == 0


def test_failed_publication_recorded(client, rendered_clip, account, monkeypatch) -> None:
    from app.services.publish import publish_service
    from app.services.publish.base import PlatformError

    monkeypatch.setattr(
        publish_service, "get_publisher",
        lambda platform, **kw: FakePublisher(fail_with=PlatformError("network_error", "down")),
    )
    clip_id, _ = rendered_clip
    _schedule(client, clip_id, account["id"])
    results = _process(client)
    assert results["failed"] == 1
    item = client.get("/api/v1/publications").json()["items"][0]
    assert item["status"] == "failed"
    assert "network_error" in item["last_error"]
