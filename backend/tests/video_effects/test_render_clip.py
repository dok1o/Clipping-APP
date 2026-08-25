from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.infra.database import get_session
from app.infra.models import Clip, RenderedAsset, Video
from app.infra.storage import get_object_storage
from app.main import app
from app.video_effects import router as render_router
from app.video_effects.renderer import FfmpegRenderError
from app.video_effects.router import CLIP_STATUS_FAILED, CLIP_STATUS_RENDERED


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_render_clip_creates_rendered_asset_and_uses_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    video = _video()
    clip = _clip(video.id)
    fake_session = FakeSession(videos={video.id: video}, clips={clip.id: clip})
    fake_storage = FakeStorage(existing_keys={video.storage_key})
    render_calls: list[dict[str, object]] = []

    def fake_render(input_path: Path, output_path: Path, start: float, duration: float) -> None:
        render_calls.append(
            {
                "input_path": input_path,
                "output_path": output_path,
                "temp_dir": output_path.parent,
                "start": start,
                "duration": duration,
            }
        )
        assert input_path.read_bytes() == b"source-video"
        output_path.write_bytes(b"rendered-video")

    monkeypatch.setattr(render_router, "render_vertical_clip", fake_render)
    client = _client(fake_session, fake_storage)

    response = client.post(f"/clips/{clip.id}/render")

    assert response.status_code == 201
    data = response.json()
    asset_id = UUID(data["id"])
    assert data["clip_id"] == str(clip.id)
    assert data["format"] == "mp4"
    assert data["width"] == 1080
    assert data["height"] == 1920
    assert data["duration"] == 8.5
    assert fake_session.rendered_assets[asset_id].clip_id == clip.id
    assert fake_session.rendered_assets[asset_id] in clip.rendered_assets
    assert clip.status == CLIP_STATUS_RENDERED
    assert fake_storage.exists_calls == [video.storage_key]
    assert fake_storage.downloads == [(video.storage_key, b"source-video")]
    assert fake_storage.uploads == [(data["storage_key"], b"rendered-video")]
    assert render_calls[0]["start"] == 1.5
    assert render_calls[0]["duration"] == 8.5
    assert not Path(render_calls[0]["temp_dir"]).exists()


def test_render_unknown_clip_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(render_router, "render_vertical_clip", _unexpected_render)
    client = _client(FakeSession(), FakeStorage(existing_keys=set()))

    response = client.post(f"/clips/{uuid4()}/render")

    assert response.status_code == 404


def test_render_missing_source_object_returns_controlled_error(monkeypatch: pytest.MonkeyPatch) -> None:
    video = _video()
    clip = _clip(video.id)
    fake_session = FakeSession(videos={video.id: video}, clips={clip.id: clip})
    fake_storage = FakeStorage(existing_keys=set())
    monkeypatch.setattr(render_router, "render_vertical_clip", _unexpected_render)
    client = _client(fake_session, fake_storage)

    response = client.post(f"/clips/{clip.id}/render")

    assert response.status_code == 404
    assert clip.status == CLIP_STATUS_FAILED
    assert fake_session.rendered_assets == {}


def test_ffmpeg_failure_marks_clip_failed_without_asset(monkeypatch: pytest.MonkeyPatch) -> None:
    video = _video()
    clip = _clip(video.id)
    fake_session = FakeSession(videos={video.id: video}, clips={clip.id: clip})
    fake_storage = FakeStorage(existing_keys={video.storage_key})

    def fail_render(input_path: Path, output_path: Path, start: float, duration: float) -> None:
        raise FfmpegRenderError("boom")

    monkeypatch.setattr(render_router, "render_vertical_clip", fail_render)
    client = _client(fake_session, fake_storage)

    response = client.post(f"/clips/{clip.id}/render")

    assert response.status_code == 500
    assert response.json()["detail"] == "ffmpeg render failed"
    assert clip.status == CLIP_STATUS_FAILED
    assert fake_session.rendered_assets == {}
    assert fake_storage.uploads == []


def test_get_rendered_assets_returns_metadata() -> None:
    video = _video()
    clip = _clip(video.id)
    asset = _rendered_asset(clip.id)
    clip.rendered_assets.append(asset)
    client = _client(
        FakeSession(
            videos={video.id: video},
            clips={clip.id: clip},
            rendered_assets={asset.id: asset},
        ),
        FakeStorage(existing_keys={video.storage_key}),
    )

    response = client.get(f"/clips/{clip.id}/rendered-assets")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(asset.id),
            "clip_id": str(clip.id),
            "storage_key": asset.storage_key,
            "format": "mp4",
            "width": 1080,
            "height": 1920,
            "duration": 8.5,
            "created_at": asset.created_at.isoformat().replace("+00:00", "Z"),
        }
    ]


def _client(fake_session: FakeSession, fake_storage: FakeStorage) -> TestClient:
    app.dependency_overrides[get_session] = lambda: fake_session
    app.dependency_overrides[get_object_storage] = lambda: fake_storage
    return TestClient(app)


def _video() -> Video:
    return Video(
        id=uuid4(),
        source_path=None,
        storage_key=f"videos/{uuid4()}/source.mp4",
        original_filename="source.mp4",
        status="uploaded",
        created_at=datetime.now(UTC),
    )


def _clip(video_id: UUID) -> Clip:
    return Clip(
        id=uuid4(),
        video_id=video_id,
        start=Decimal("1.5"),
        end=Decimal("10.0"),
        status="created",
        created_at=datetime.now(UTC),
    )


def _rendered_asset(clip_id: UUID) -> RenderedAsset:
    return RenderedAsset(
        id=uuid4(),
        clip_id=clip_id,
        storage_key=f"rendered_assets/{clip_id}/{uuid4()}.mp4",
        format="mp4",
        width=1080,
        height=1920,
        duration=Decimal("8.5"),
        created_at=datetime.now(UTC),
    )


def _unexpected_render(input_path: Path, output_path: Path, start: float, duration: float) -> None:
    raise AssertionError("ffmpeg should not be called")


class FakeSession:
    def __init__(
        self,
        videos: dict[UUID, Video] | None = None,
        clips: dict[UUID, Clip] | None = None,
        rendered_assets: dict[UUID, RenderedAsset] | None = None,
    ) -> None:
        self.videos = videos or {}
        self.clips = clips or {}
        self.rendered_assets = rendered_assets or {}
        self.commits = 0
        self.rolled_back = False

    def add(self, entity: Video | Clip | RenderedAsset) -> None:
        if isinstance(entity, Video):
            self.videos[entity.id] = entity
            return
        if isinstance(entity, Clip):
            self.clips[entity.id] = entity
            return
        self.rendered_assets[entity.id] = entity
        clip = self.clips.get(entity.clip_id)
        if clip is not None and entity not in clip.rendered_assets:
            clip.rendered_assets.append(entity)

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, entity: Video | Clip | RenderedAsset) -> None:
        return None

    def rollback(self) -> None:
        self.rolled_back = True

    def get(self, model, entity_id: UUID):
        if model is Video:
            return self.videos.get(entity_id)
        if model is Clip:
            return self.clips.get(entity_id)
        if model is RenderedAsset:
            return self.rendered_assets.get(entity_id)
        return None


class FakeStorage:
    def __init__(self, existing_keys: set[str | None]) -> None:
        self.existing_keys = existing_keys
        self.exists_calls: list[str] = []
        self.downloads: list[tuple[str, bytes]] = []
        self.uploads: list[tuple[str, bytes]] = []

    def exists(self, object_key: str) -> bool:
        self.exists_calls.append(object_key)
        return object_key in self.existing_keys

    def download_file(self, object_key: str, destination_path: str | Path) -> None:
        data = b"source-video"
        Path(destination_path).write_bytes(data)
        self.downloads.append((object_key, data))

    def upload_file(self, file_path: str | Path, object_key: str) -> None:
        self.uploads.append((object_key, Path(file_path).read_bytes()))
