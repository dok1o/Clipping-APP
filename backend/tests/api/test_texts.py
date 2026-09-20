"""Texts API contract tests (fake provider, default LLM_BACKEND=fake)."""
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
        json={"title": "Как монтировать клипы", "start_sec": 0.0, "end_sec": 15.0},
    ).json()
    return clip["id"]


def test_generate_texts_200(client, clip_id) -> None:
    response = client.post(
        "/api/v1/texts/generate",
        json={"clip_id": clip_id, "platform": "youtube"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job_id"] is None  # synchronous Stage 2
    assert len(body["texts"]["titles"]) == 3
    assert all(len(t) <= 100 for t in body["texts"]["titles"])  # YouTube limit
    assert 3 <= len(body["texts"]["hashtags"]) <= 8
    assert body["platform"] == "youtube"


def test_generate_texts_tiktok_limits(client, clip_id) -> None:
    body = client.post(
        "/api/v1/texts/generate", json={"clip_id": clip_id, "platform": "tiktok"}
    ).json()
    assert all(len(t) <= 2200 for t in body["texts"]["titles"])
    assert len(body["texts"]["titles"]) == 3


def test_generate_with_transcript_and_tone(client, clip_id) -> None:
    body = client.post(
        "/api/v1/texts/generate",
        json={
            "clip_id": clip_id, "platform": "youtube", "tone": "экспертный",
            "transcript": "смотри главное про монтаж клипов",
        },
    ).json()
    assert len(body["texts"]["titles"]) == 3


def test_get_clip_texts_roundtrip(client, clip_id) -> None:
    client.post("/api/v1/texts/generate", json={"clip_id": clip_id, "platform": "youtube"})
    got = client.get(f"/api/v1/clips/{clip_id}/texts", params={"platform": "youtube"})
    assert got.status_code == 200
    body = got.json()
    assert body["texts"] is not None
    assert len(body["texts"]["titles"]) == 3


def test_get_clip_texts_empty_for_other_platform(client, clip_id) -> None:
    client.post("/api/v1/texts/generate", json={"clip_id": clip_id, "platform": "youtube"})
    body = client.get(f"/api/v1/clips/{clip_id}/texts", params={"platform": "tiktok"}).json()
    assert body["texts"] is None


def test_generate_clip_not_found(client) -> None:
    response = client.post(
        "/api/v1/texts/generate", json={"clip_id": str(uuid.uuid4()), "platform": "youtube"}
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "clip_not_found"


def test_generate_invalid_platform_422(client, clip_id) -> None:
    response = client.post(
        "/api/v1/texts/generate", json={"clip_id": clip_id, "platform": "vimeo"}
    )
    assert response.status_code == 422


def test_generate_provider_error_502(client, clip_id, monkeypatch) -> None:
    from app.services.text_gen import text_service
    from app.services.text_gen.base import TextGenError

    class Broken:
        name = "broken"

        def generate(self, *a, **k):
            raise TextGenError("provider_unavailable", "ollama unreachable at http://x")

    monkeypatch.setattr(text_service, "get_provider", lambda: Broken())
    response = client.post(
        "/api/v1/texts/generate", json={"clip_id": clip_id, "platform": "youtube"}
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "text_gen_error"
    # failed job recorded with error
    from app.db import session as db_session
    from app.models.job import Job

    db = db_session.session_factory()
    jobs = db.query(Job).filter(Job.ref_id == uuid.UUID(clip_id)).all()
    assert any(j.status == "failed" and "provider_unavailable" in (j.error_message or "") for j in jobs)
    db.close()
