from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.infra.config import UploadSettings, get_upload_settings
from app.infra.database import get_session
from app.infra.models import Video
from app.infra.storage import get_object_storage
from app.ingestion.router import VIDEO_CREATED_STATUS
from app.main import app


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_video_upload_creates_video_and_uses_storage() -> None:
    fake_session = FakeSession()
    fake_storage = FakeStorage()
    client = _client(fake_session, fake_storage)

    response = client.post(
        "/videos",
        files={"file": ("sample.mp4", b"video-bytes", "video/mp4")},
    )

    assert response.status_code == 201
    data = response.json()
    video_id = UUID(data["id"])
    assert data["original_filename"] == "sample.mp4"
    assert data["status"] == VIDEO_CREATED_STATUS
    assert "created_at" in data

    created_video = fake_session.videos[video_id]
    assert created_video.original_filename == "sample.mp4"
    assert created_video.status == VIDEO_CREATED_STATUS
    assert created_video.storage_key == fake_storage.uploads[0]["object_key"]
    assert fake_storage.uploads[0]["content_type"] == "video/mp4"


def test_empty_video_upload_is_rejected() -> None:
    client = _client(FakeSession(), FakeStorage())

    response = client.post(
        "/videos",
        files={"file": ("empty.mp4", b"", "video/mp4")},
    )

    assert response.status_code == 400


def test_unsupported_media_type_is_rejected() -> None:
    client = _client(FakeSession(), FakeStorage())

    response = client.post(
        "/videos",
        files={"file": ("notes.txt", b"not-video", "text/plain")},
    )

    assert response.status_code == 415


def test_get_video_returns_minimal_metadata() -> None:
    fake_session = FakeSession()
    fake_storage = FakeStorage()
    client = _client(fake_session, fake_storage)
    upload_response = client.post(
        "/videos",
        files={"file": ("sample.webm", b"video-bytes", "video/webm")},
    )
    video_id = upload_response.json()["id"]

    response = client.get(f"/videos/{video_id}")

    assert response.status_code == 200
    assert response.json() == upload_response.json()


def test_get_unknown_video_returns_404() -> None:
    client = _client(FakeSession(), FakeStorage())

    response = client.get(f"/videos/{uuid4()}")

    assert response.status_code == 404


def _client(fake_session: FakeSession, fake_storage: FakeStorage) -> TestClient:
    app.dependency_overrides[get_session] = lambda: fake_session
    app.dependency_overrides[get_object_storage] = lambda: fake_storage
    app.dependency_overrides[get_upload_settings] = lambda: UploadSettings(video_upload_max_bytes=1024)
    return TestClient(app)


class FakeSession:
    def __init__(self) -> None:
        self.videos: dict[UUID, Video] = {}
        self.committed = False
        self.rolled_back = False

    def add(self, video: Video) -> None:
        self.videos[video.id] = video

    def commit(self) -> None:
        self.committed = True

    def refresh(self, video: Video) -> None:
        return None

    def rollback(self) -> None:
        self.rolled_back = True

    def get(self, model, video_id: UUID):
        if model is Video:
            return self.videos.get(video_id)
        return None


class FakeStorage:
    def __init__(self) -> None:
        self.uploads = []

    def upload_fileobj(self, fileobj, object_key: str, content_type: str | None = None) -> None:
        self.uploads.append(
            {
                "object_key": object_key,
                "content_type": content_type,
                "bytes": fileobj.read(),
            }
        )
