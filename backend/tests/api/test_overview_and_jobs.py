"""Stage 10 dashboard APIs: job list, overview aggregate, clip PATCH."""
import io


def _video(client, name="v.mp4"):
    return client.post(
        "/api/v1/videos",
        files={"file": (name, io.BytesIO(b"\x00\x00\x00\x18ftypmp42data"), "video/mp4")},
    ).json()


def test_list_jobs_filters_and_pagination(client, monkeypatch) -> None:
    from pathlib import Path

    from app.services.render import render_service

    monkeypatch.setattr(
        render_service, "render_vertical",
        lambda s, d, **k: Path(d).write_bytes(b"r"),
    )
    video = _video(client)
    clip = client.post(
        f"/api/v1/videos/{video['id']}/clips/manual",
        json={"title": "t", "start_sec": 0.0, "end_sec": 10.0},
    ).json()
    client.post(f"/api/v1/clips/{clip['id']}/render")  # eager -> succeeded job

    page = client.get("/api/v1/jobs").json()
    assert page["total"] >= 1
    assert page["items"][0]["type"] in ("render",)

    only_failed = client.get("/api/v1/jobs?status=failed").json()
    assert only_failed["total"] == 0
    limited = client.get("/api/v1/jobs?limit=1").json()
    assert len(limited["items"]) == 1
    typed = client.get("/api/v1/jobs?type=render&status=succeeded").json()
    assert typed["total"] >= 1


def test_overview_counts_pipeline(client, monkeypatch) -> None:
    from pathlib import Path

    from app.services.render import render_service

    monkeypatch.setattr(
        render_service, "render_vertical",
        lambda s, d, **k: Path(d).write_bytes(b"r"),
    )
    video = _video(client)
    clip = client.post(
        f"/api/v1/videos/{video['id']}/clips/manual",
        json={"title": "t", "start_sec": 0.0, "end_sec": 10.0},
    ).json()
    client.post(f"/api/v1/clips/{clip['id']}/render")

    data = client.get("/api/v1/overview").json()
    assert data["videos"].get("ready") == 1
    assert data["clips"].get("rendered") == 1
    assert data["jobs"].get("succeeded", 0) >= 1
    assert data["publications"] == {} or isinstance(data["publications"], dict)
    assert data["ml"]["dataset_rows"] == 0
    assert data["ml"]["active_model"] is None
    assert data["latest_metrics"]["views"] == 0
    assert data["failed_jobs_recent"] == 0


def test_patch_clip_draft(client) -> None:
    video = _video(client)
    clip = client.post(
        f"/api/v1/videos/{video['id']}/clips/manual",
        json={"title": "old", "start_sec": 0.0, "end_sec": 10.0},
    ).json()
    patched = client.patch(
        f"/api/v1/clips/{clip['id']}",
        json={"title": "new title", "start_sec": 2.0, "end_sec": 12.0},
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["title"] == "new title"
    assert body["start_sec"] == 2.0 and body["end_sec"] == 12.0


def test_patch_clip_invalid_range_rejected(client) -> None:
    video = _video(client)
    clip = client.post(
        f"/api/v1/videos/{video['id']}/clips/manual",
        json={"title": "t", "start_sec": 0.0, "end_sec": 10.0},
    ).json()
    resp = client.patch(
        f"/api/v1/clips/{clip['id']}", json={"start_sec": 10.0, "end_sec": 10.0}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_range"


def test_patch_clip_not_editable_after_render(client, monkeypatch) -> None:
    from pathlib import Path

    from app.services.render import render_service

    monkeypatch.setattr(
        render_service, "render_vertical",
        lambda s, d, **k: Path(d).write_bytes(b"r"),
    )
    video = _video(client)
    clip = client.post(
        f"/api/v1/videos/{video['id']}/clips/manual",
        json={"title": "t", "start_sec": 0.0, "end_sec": 10.0},
    ).json()
    client.post(f"/api/v1/clips/{clip['id']}/render")
    resp = client.patch(f"/api/v1/clips/{clip['id']}", json={"title": "x"})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "clip_not_editable"


def test_ml_active_model_none_without_training(client) -> None:
    data = client.get("/api/v1/ml/active-model").json()
    assert data == {"active": False, "model_version": None}


def test_get_clip_asset_after_render(client, monkeypatch) -> None:
    from pathlib import Path

    from app.services.render import render_service

    monkeypatch.setattr(
        render_service, "render_vertical",
        lambda s, d, **k: Path(d).write_bytes(b"r"),
    )
    video = _video(client)
    clip = client.post(
        f"/api/v1/videos/{video['id']}/clips/manual",
        json={"title": "t", "start_sec": 0.0, "end_sec": 10.0},
    ).json()
    missing = client.get(f"/api/v1/clips/{clip['id']}/asset")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "asset_not_found"

    client.post(f"/api/v1/clips/{clip['id']}/render")
    found = client.get(f"/api/v1/clips/{clip['id']}/asset")
    assert found.status_code == 200
    body = found.json()
    assert body["clip_id"] == clip["id"]
    assert body["width"] == 1080 and body["height"] == 1920
