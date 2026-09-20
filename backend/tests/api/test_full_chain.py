"""Stage 3 acceptance gate: the full chain on mocks/synthetics (no real services).

upload -> transcribe (mocked whisper) -> candidates (mocked scenes) -> promote
-> render (faked ffmpeg) -> texts (fake provider)
"""
import io
import uuid
from pathlib import Path


def test_stage3_full_chain(client, monkeypatch) -> None:
    # --- mocks: whisper, scenes, ffmpeg render ---
    segments = [
        {"start": 0.0, "end": 8.0, "text": "смотри главное правило монтажа клипов", "avg_confidence": 0.9},
        {"start": 8.0, "end": 16.0, "text": "секрет в скорости и ритме", "avg_confidence": 0.85},
        {"start": 90.0, "end": 100.0, "text": "итак подведём итог", "avg_confidence": 0.8},
    ]
    info = {"device_used": "cpu", "compute_type": "int8", "model": "small", "duration": 100.0, "language": "ru"}
    monkeypatch.setattr(
        "app.services.transcription.whisper_service.extract_audio_wav",
        lambda s, d, **k: Path(d).write_bytes(b"wav"),
    )
    monkeypatch.setattr(
        "app.services.transcription.whisper_service.transcribe_audio",
        lambda wav, **kw: (segments, info),
    )
    monkeypatch.setattr(
        "app.services.ai_clipping.candidate_service.scene_service.detect_scenes",
        lambda src, **kw: [0.0, 30.0, 60.0, 90.0],
    )
    monkeypatch.setattr(
        "app.services.ai_clipping.candidate_service.extract_audio_wav",
        lambda s, d, **k: None,
    )
    monkeypatch.setattr(
        "app.services.render.render_service.render_vertical",
        lambda s, d, **k: Path(d).write_bytes(b"rendered"),
    )

    # 1) upload
    video = client.post(
        "/api/v1/videos",
        files={"file": ("v.mp4", io.BytesIO(b"\x00\x00\x00\x18ftypmp42data"), "video/mp4")},
    ).json()
    assert video["status"] == "ready"

    # duration is required for windows — set it (no ffprobe in test env)
    from app.db import session as db_session
    from app.models.video import Video

    db = db_session.session_factory()
    db.get(Video, uuid.UUID(video["id"])).duration_sec = 100.0
    db.commit()
    db.close()

    # 2) transcribe
    tr = client.post(f"/api/v1/videos/{video['id']}/transcribe")
    assert tr.status_code == 202
    assert client.get(f"/api/v1/jobs/{tr.json()['job_id']}").json()["status"] == "succeeded"
    assert client.get(f"/api/v1/videos/{video['id']}/transcript").json()["total"] == 3

    # 3) candidates
    candidates = client.post(f"/api/v1/videos/{video['id']}/candidates", params={"top_k": 5})
    assert candidates.status_code == 200
    assert candidates.json()["total"] == 5

    # 4) promote the top candidate
    top = candidates.json()["items"][0]
    clip = client.post(f"/api/v1/candidates/{top['id']}/promote")
    assert clip.status_code == 201
    clip_id = clip.json()["id"]

    # 5) render
    render = client.post(f"/api/v1/clips/{clip_id}/render")
    assert render.status_code == 202
    job = client.get(f"/api/v1/jobs/{render.json()['id']}").json()
    assert job["status"] == "succeeded", job.get("error_message")
    asset_id = job["result"]["asset_id"]
    assert client.get(f"/api/v1/renders/{asset_id}").json()["status"] == "ready"

    # 6) texts for both platforms
    for platform, title_limit in (("youtube", 100), ("tiktok", 2200)):
        texts = client.post(
            "/api/v1/texts/generate", json={"clip_id": clip_id, "platform": platform}
        )
        assert texts.status_code == 200
        body = texts.json()
        assert len(body["texts"]["titles"]) == 3
        assert all(len(t) <= title_limit for t in body["texts"]["titles"])
        stored = client.get(f"/api/v1/clips/{clip_id}/texts", params={"platform": platform})
        assert stored.json()["texts"] is not None
