"""Videos API contract tests (multipart upload via moto S3)."""
import io
import uuid

from app.core.config import get_settings


def _file(name: str = "clip.mp4", data: bytes = b"\x00\x00\x00\x18ftypmp42fake", mime: str = "video/mp4"):
    return {"file": (name, io.BytesIO(data), mime)}


def test_upload_201(client, s3_mock) -> None:
    response = client.post("/api/v1/videos", files=_file())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["original_filename"] == "clip.mp4"
    assert body["status"] == "ready"
    assert body["mime_type"] == "video/mp4"
    assert body["size_bytes"] > 0
    assert body["created_at"].endswith("Z")
    assert s3_mock.exists(body["storage_key"]) is True
    assert body["storage_key"].startswith(f"videos/{body['id']}/")
    assert body["duration_sec"] is None  # no ffprobe in sandbox


def test_upload_rejects_wrong_extension(client) -> None:
    response = client.post("/api/v1/videos", files=_file("movie.avi", b"data"))
    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "unsupported_media"


def test_upload_rejects_wrong_mime(client) -> None:
    response = client.post("/api/v1/videos", files=_file("movie.mp4", b"data", "image/png"))
    assert response.status_code == 415


def test_upload_rejects_empty_file(client) -> None:
    response = client.post("/api/v1/videos", files=_file("empty.mp4", b""))
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "empty_file"


def test_upload_413_when_over_limit(client, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "upload_max_mb", 0)
    response = client.post("/api/v1/videos", files=_file())
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "payload_too_large"


def test_upload_video_row_failed_on_storage_error(client, monkeypatch) -> None:
    from app.services.ingest import upload_service as svc

    def boom(*args, **kwargs):
        raise RuntimeError("s3 down")

    monkeypatch.setattr(svc, "storage_upload", None, raising=False)
    monkeypatch.setattr("app.services.ingest.upload_service.storage", None, raising=False)
    # patch the S3Storage method used inside create_video
    monkeypatch.setattr("app.infra.s3.S3Storage.upload_file", boom)
    response = client.post("/api/v1/videos", files=_file())
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "storage_error"


def test_list_videos_pagination(client) -> None:
    for _ in range(3):
        assert client.post("/api/v1/videos", files=_file()).status_code == 201
    page = client.get("/api/v1/videos", params={"limit": 2, "offset": 0}).json()
    assert len(page["items"]) == 2
    assert page["total"] == 3
    page2 = client.get("/api/v1/videos", params={"limit": 2, "offset": 2}).json()
    assert len(page2["items"]) == 1


def test_get_video_by_id(client) -> None:
    created = client.post("/api/v1/videos", files=_file()).json()
    got = client.get(f"/api/v1/videos/{created['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == created["id"]


def test_get_video_not_found(client) -> None:
    response = client.get(f"/api/v1/videos/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "video_not_found"


def test_get_video_invalid_uuid(client) -> None:
    response = client.get("/api/v1/videos/not-a-uuid")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "validation_error"
