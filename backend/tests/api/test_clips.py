"""Manual clip API contract tests (§12): NO ffprobe in this flow."""
import io
import uuid

import pytest


@pytest.fixture
def ready_video(client):
    body = client.post(
        "/api/v1/videos",
        files={"file": ("v.mp4", io.BytesIO(b"\x00\x00\x00\x18ftypmp42data"), "video/mp4")},
    ).json()
    return body


def _create(client, video_id, title="Best moment", start=10.0, end=40.0):
    return client.post(
        f"/api/v1/videos/{video_id}/clips/manual",
        json={"title": title, "start_sec": start, "end_sec": end},
    )


def test_create_manual_clip_201(client, ready_video) -> None:
    response = _create(client, ready_video["id"], start=12.5, end=42.0)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "draft"
    assert body["video_id"] == ready_video["id"]
    assert body["start_sec"] == 12.5
    assert body["created_at"].endswith("Z")


def test_boundary_5s_ok_and_4_99_fails(client, ready_video) -> None:
    assert _create(client, ready_video["id"], start=0.0, end=5.0).status_code == 201
    resp = _create(client, ready_video["id"], start=0.0, end=4.99)
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "clip_too_short"


def test_boundary_180s_ok_and_over_fails(client, ready_video) -> None:
    assert _create(client, ready_video["id"], start=0.0, end=180.0).status_code == 201
    resp = _create(client, ready_video["id"], start=0.0, end=180.01)
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "clip_too_long"


def test_end_leq_start_invalid_range(client, ready_video) -> None:
    resp = _create(client, ready_video["id"], start=10.0, end=10.0)
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_range"
    resp2 = _create(client, ready_video["id"], start=10.0, end=5.0)
    assert resp2.status_code == 400


def test_negative_start_422(client, ready_video) -> None:
    resp = _create(client, ready_video["id"], start=-1.0, end=10.0)
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "validation_error"


def test_title_limits(client, ready_video) -> None:
    assert _create(client, ready_video["id"], title="").status_code == 422
    assert _create(client, ready_video["id"], title="x" * 141).status_code == 422
    assert _create(client, ready_video["id"], title="x" * 140).status_code == 201


def test_video_not_found(client) -> None:
    resp = _create(client, uuid.uuid4())
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "video_not_found"


def test_video_not_ready_409(client, db, ready_video) -> None:
    from app.models.video import Video, VideoStatus

    video = db.get(Video, uuid.UUID(ready_video["id"]))
    video.status = VideoStatus.UPLOADING
    db.commit()
    resp = _create(client, ready_video["id"])
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "video_not_ready"


def test_end_beyond_known_duration_400(client, db, ready_video) -> None:
    from app.models.video import Video

    video = db.get(Video, uuid.UUID(ready_video["id"]))
    video.duration_sec = 50.0
    db.commit()
    assert _create(client, ready_video["id"], start=10.0, end=45.0).status_code == 201
    resp = _create(client, ready_video["id"], start=10.0, end=60.0)
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_range"


def test_duration_null_skips_bound_check(client, ready_video) -> None:
    # fresh upload has duration_sec == null (no ffprobe in sandbox) => no upper bound
    assert ready_video["duration_sec"] is None
    assert _create(client, ready_video["id"], start=0.0, end=180.0).status_code == 201


def test_no_ffprobe_in_manual_clip_flow(client, ready_video, monkeypatch) -> None:
    """Mock assert: probe_media must NOT be called during manual clip creation."""
    from app.services.render import ffmpeg_runner

    def _fail(*args, **kwargs):
        raise AssertionError("ffprobe must not be called in manual clip flow")

    monkeypatch.setattr(ffmpeg_runner, "probe_media", _fail)
    assert _create(client, ready_video["id"]).status_code == 201


def test_list_clips_by_video(client, ready_video) -> None:
    _create(client, ready_video["id"], title="one", start=0.0, end=10.0)
    _create(client, ready_video["id"], title="two", start=20.0, end=40.0)
    page = client.get("/api/v1/clips", params={"video_id": ready_video["id"]}).json()
    assert page["total"] == 2
    assert {item["title"] for item in page["items"]} == {"one", "two"}


def test_get_clip_404(client) -> None:
    resp = client.get(f"/api/v1/clips/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "clip_not_found"
