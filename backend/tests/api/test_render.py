"""Render API: 202 + Job lifecycle + idempotency (render faked — machine-independent)."""
import io
import uuid

import pytest


@pytest.fixture
def clip_id(client) -> str:
    video = client.post(
        "/api/v1/videos",
        files={"file": ("v.mp4", io.BytesIO(b"\x00\x00\x00\x18ftypmp42data"), "video/mp4")},
    ).json()
    clip = client.post(
        f"/api/v1/videos/{video['id']}/clips/manual",
        json={"title": "moment", "start_sec": 1.0, "end_sec": 10.0},
    ).json()
    return clip["id"]


@pytest.fixture
def fake_render(monkeypatch, tmp_path):
    """Replace real ffmpeg with a fake that 'renders' a valid output file."""
    from app.services.render import render_service

    def fake_render_vertical(src, dst, *, start_sec, duration_sec, **kwargs):
        Path = type(dst)
        dst.write_bytes(b"fake-mp4-rendered-output")

    monkeypatch.setattr(render_service, "render_vertical", fake_render_vertical)
    return fake_render_vertical


def test_render_202_and_job_lifecycle(client, clip_id, fake_render, s3_mock) -> None:
    response = client.post(f"/api/v1/clips/{clip_id}/render")
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["clip_id"] if "clip_id" in body else True
    job_id = body["id"]

    job = client.get(f"/api/v1/jobs/{job_id}").json()
    assert job["status"] == "succeeded"
    assert job["type"] == "render"
    assert job["result"]["asset_id"]

    # clip transitions to rendered
    clip = client.get(f"/api/v1/clips/{clip_id}").json()
    assert clip["status"] == "rendered"

    # asset readable + stored in S3 + presigned download
    asset_id = job["result"]["asset_id"]
    asset = client.get(f"/api/v1/renders/{asset_id}").json()
    assert asset["width"] == 1080 and asset["height"] == 1920
    assert asset["codec_video"] == "h264" and asset["codec_audio"] == "aac"
    assert asset["pix_fmt"] == "yuv420p"
    assert asset["status"] == "ready"
    assert s3_mock.exists(asset["storage_key"])
    dl = client.get(f"/api/v1/renders/{asset_id}/download").json()
    assert "url" in dl and dl["expires_sec"] == 900


def test_render_idempotent_when_rendered(client, clip_id, fake_render) -> None:
    first = client.post(f"/api/v1/clips/{clip_id}/render").json()
    second = client.post(f"/api/v1/clips/{clip_id}/render")
    assert second.status_code == 202
    assert second.json()["id"] == first["id"]  # same job returned
    assert second.json()["status"] == "succeeded"


def test_render_conflict_while_in_progress(client, clip_id, monkeypatch) -> None:
    # keep the job queued: neutralize the eager task dispatch
    from app.workers import tasks

    monkeypatch.setattr(tasks.render_task, "delay", lambda *a, **k: None)
    first = client.post(f"/api/v1/clips/{clip_id}/render")
    assert first.status_code == 202
    conflict = client.post(f"/api/v1/clips/{clip_id}/render")
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "already_rendering"


def test_render_failure_marks_clip_failed(client, clip_id, monkeypatch) -> None:
    from app.services.render import render_service
    from app.services.render.ffmpeg_runner import RenderError

    def boom(*args, **kwargs):
        raise RenderError("render_failed", "ffmpeg exploded", stderr_tail="x" * 5000)

    monkeypatch.setattr(render_service, "render_vertical", boom)
    response = client.post(f"/api/v1/clips/{clip_id}/render")
    assert response.status_code == 202
    job = client.get(f"/api/v1/jobs/{response.json()['id']}").json()
    assert job["status"] == "failed"
    assert "render_failed" in job["error_message"]
    assert len(job["error_message"]) < 2200  # stderr tail truncated to 2KB
    clip = client.get(f"/api/v1/clips/{clip_id}").json()
    assert clip["status"] == "render_failed"

    # retry after failure is allowed (fresh job)
    monkeypatch.setattr(
        render_service, "render_vertical",
        lambda s, d, **k: type(d).write_bytes if False else _write(d),
    )
    retry = client.post(f"/api/v1/clips/{clip_id}/render")
    assert retry.status_code == 202


def _write(dst):
    import pathlib

    pathlib.Path(dst).write_bytes(b"ok")


def test_render_clip_not_found(client) -> None:
    response = client.post(f"/api/v1/clips/{uuid.uuid4()}/render")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "clip_not_found"


def test_render_asset_not_found(client) -> None:
    assert client.get(f"/api/v1/renders/{uuid.uuid4()}").status_code == 404
    assert client.get(f"/api/v1/renders/{uuid.uuid4()}/download").status_code == 404
