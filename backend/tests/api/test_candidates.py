"""Candidates API: generate -> list -> promote (scenes/loudness mocked at binary level)."""
import io
import uuid
from unittest.mock import patch

import pytest


@pytest.fixture
def video_with_transcript(client):
    video = client.post(
        "/api/v1/videos",
        files={"file": ("v.mp4", io.BytesIO(b"\x00\x00\x00\x18ftypmp42data"), "video/mp4")},
    ).json()
    # set duration + transcript segments directly
    from app.db import session as db_session
    from app.models.transcript import TranscriptSegment
    from app.models.video import Video

    db = db_session.session_factory()
    v = db.get(Video, uuid.UUID(video["id"]))
    v.duration_sec = 120.0
    db.commit()
    for start, end, text in [
        (0.0, 8.0, "смотри главное правило монтажа"),
        (8.0, 16.0, "секрет в том что"),
        (60.0, 70.0, "обычная речь"),
        (100.0, 110.0, "итак итог и вопрос"),
    ]:
        db.add(TranscriptSegment(video_id=v.id, start=start, end=end, text=text))
    db.commit()
    db.close()
    return video


@pytest.fixture
def fake_media(monkeypatch):
    """Scene detection returns boundaries; audio extraction produces a real tiny wav."""
    monkeypatch.setattr(
        "app.services.ai_clipping.candidate_service.scene_service.detect_scenes",
        lambda src, **kw: [0.0, 30.0, 60.0, 90.0, 110.0],
    )

    def fake_extract(src, dst, **kwargs):
        import struct
        import wave
        from pathlib import Path

        with wave.open(str(dst), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            for _ in range(5):  # 5 seconds of loud-ish noise
                frames = b"".join(struct.pack("<h", 12000 if i % 2 else 6000) for i in range(16000))
                wav.writeframes(frames)

    monkeypatch.setattr(
        "app.services.ai_clipping.candidate_service.extract_audio_wav", fake_extract
    )


def test_generate_candidates_top_k(client, video_with_transcript, fake_media) -> None:
    response = client.post(
        f"/api/v1/videos/{video_with_transcript['id']}/candidates", params={"top_k": 3}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3
    scores = [c["score"] for c in body["items"]]
    assert scores == sorted(scores, reverse=True)
    top = body["items"][0]
    assert 5.0 <= top["end"] - top["start"] <= 60.0
    assert "features" in top and "speech_ratio" in top["features"]
    assert top["reason"]


def test_candidates_deterministic(client, video_with_transcript, fake_media) -> None:
    a = client.post(f"/api/v1/videos/{video_with_transcript['id']}/candidates").json()
    b = client.post(f"/api/v1/videos/{video_with_transcript['id']}/candidates").json()
    assert [(c["start"], c["end"], round(c["score"], 4)) for c in a["items"]] == \
           [(c["start"], c["end"], round(c["score"], 4)) for c in b["items"]]


def test_generate_requires_transcript(client) -> None:
    video = client.post(
        "/api/v1/videos",
        files={"file": ("v2.mp4", io.BytesIO(b"data"), "video/mp4")},
    ).json()
    response = client.post(f"/api/v1/videos/{video['id']}/candidates")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "transcript_missing"


def test_promote_creates_clip(client, video_with_transcript, fake_media) -> None:
    candidates = client.post(
        f"/api/v1/videos/{video_with_transcript['id']}/candidates", params={"top_k": 5}
    ).json()["items"]
    top = candidates[0]
    promoted = client.post(f"/api/v1/candidates/{top['id']}/promote", json={"title": "Мой клип"})
    assert promoted.status_code == 201, promoted.text
    clip = promoted.json()
    assert clip["status"] == "draft"
    assert clip["title"] == "Мой клип"
    assert clip["start_sec"] == top["start"]
    assert clip["score"] == top["score"]

    # default title from transcript when not provided
    auto = client.post(f"/api/v1/candidates/{candidates[1]['id']}/promote")
    assert auto.status_code == 201
    assert auto.json()["title"]


def test_promote_candidate_not_found(client) -> None:
    assert client.post(f"/api/v1/candidates/{uuid.uuid4()}/promote").status_code == 404


def test_list_candidates(client, video_with_transcript, fake_media) -> None:
    client.post(f"/api/v1/videos/{video_with_transcript['id']}/candidates")
    listing = client.get(f"/api/v1/videos/{video_with_transcript['id']}/candidates")
    assert listing.status_code == 200
    assert listing.json()["total"] >= 1


def test_scene_fallback_when_no_scenes(client, video_with_transcript, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.ai_clipping.candidate_service.scene_service.detect_scenes",
        lambda src, **kw: [],
    )
    monkeypatch.setattr(
        "app.services.ai_clipping.candidate_service.extract_audio_wav",
        lambda s, d, **k: None,  # no wav => loudness neutral
    )
    body = client.post(f"/api/v1/videos/{video_with_transcript['id']}/candidates").json()
    assert body["total"] >= 1
    assert body["items"][0]["features"]["scene_fallback"] is True
    assert body["items"][0]["features"]["scene_boundaries"]  # uniform windows used
