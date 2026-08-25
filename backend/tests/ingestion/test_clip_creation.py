from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.infra.database import get_session
from app.infra.models import Clip, Video
from app.ingestion.router import CLIP_CREATED_STATUS
from app.main import app


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_create_clip_for_video() -> None:
    video = _video()
    fake_session = FakeSession(videos={video.id: video})
    client = _client(fake_session)

    response = client.post(
        f"/videos/{video.id}/clips",
        json={"start": 1.25, "end": 8.5},
    )

    assert response.status_code == 201
    data = response.json()
    clip_id = UUID(data["id"])
    assert data["video_id"] == str(video.id)
    assert data["start"] == 1.25
    assert data["end"] == 8.5
    assert data["status"] == CLIP_CREATED_STATUS
    assert "created_at" in data

    created_clip = fake_session.clips[clip_id]
    assert created_clip.video_id == video.id
    assert created_clip in video.clips


def test_invalid_clip_timestamps_are_rejected() -> None:
    video = _video()
    client = _client(FakeSession(videos={video.id: video}))

    negative_start = client.post(
        f"/videos/{video.id}/clips",
        json={"start": -1, "end": 8.5},
    )
    end_before_start = client.post(
        f"/videos/{video.id}/clips",
        json={"start": 8.5, "end": 8.5},
    )

    assert negative_start.status_code == 422
    assert end_before_start.status_code == 422


def test_create_clip_unknown_video_returns_404() -> None:
    client = _client(FakeSession())

    response = client.post(
        f"/videos/{uuid4()}/clips",
        json={"start": 1.25, "end": 8.5},
    )

    assert response.status_code == 404


def test_get_clip_returns_metadata() -> None:
    video = _video()
    clip = _clip(video.id, start=2, end=6)
    fake_session = FakeSession(videos={video.id: video}, clips={clip.id: clip})
    client = _client(fake_session)

    response = client.get(f"/clips/{clip.id}")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(clip.id),
        "video_id": str(video.id),
        "start": 2.0,
        "end": 6.0,
        "status": CLIP_CREATED_STATUS,
        "created_at": clip.created_at.isoformat().replace("+00:00", "Z"),
    }


def test_list_video_clips_returns_clips_for_video() -> None:
    video = _video()
    clip = _clip(video.id, start=3, end=9)
    video.clips.append(clip)
    client = _client(FakeSession(videos={video.id: video}, clips={clip.id: clip}))

    response = client.get(f"/videos/{video.id}/clips")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(clip.id)
    assert data[0]["video_id"] == str(video.id)


def test_get_unknown_clip_returns_404() -> None:
    client = _client(FakeSession())

    response = client.get(f"/clips/{uuid4()}")

    assert response.status_code == 404


def _client(fake_session: FakeSession) -> TestClient:
    app.dependency_overrides[get_session] = lambda: fake_session
    return TestClient(app)


def _video() -> Video:
    return Video(
        id=uuid4(),
        source_path=None,
        storage_key="videos/example.mp4",
        original_filename="example.mp4",
        status="uploaded",
        created_at=datetime.now(UTC),
    )


def _clip(video_id: UUID, start: float, end: float) -> Clip:
    return Clip(
        id=uuid4(),
        video_id=video_id,
        start=start,
        end=end,
        status=CLIP_CREATED_STATUS,
        created_at=datetime.now(UTC),
    )


class FakeSession:
    def __init__(
        self,
        videos: dict[UUID, Video] | None = None,
        clips: dict[UUID, Clip] | None = None,
    ) -> None:
        self.videos = videos or {}
        self.clips = clips or {}
        self.committed = False
        self.rolled_back = False

    def add(self, entity: Video | Clip) -> None:
        if isinstance(entity, Video):
            self.videos[entity.id] = entity
            return
        self.clips[entity.id] = entity
        video = self.videos.get(entity.video_id)
        if video is not None and entity not in video.clips:
            video.clips.append(entity)

    def commit(self) -> None:
        self.committed = True

    def refresh(self, entity: Video | Clip) -> None:
        return None

    def rollback(self) -> None:
        self.rolled_back = True

    def get(self, model, entity_id: UUID):
        if model is Video:
            return self.videos.get(entity_id)
        if model is Clip:
            return self.clips.get(entity_id)
        return None
