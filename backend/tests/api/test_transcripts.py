"""Transcription API contract tests (whisper mocked — no model download)."""
import io
import uuid
from unittest.mock import patch

import pytest


@pytest.fixture
def video(client) -> dict:
    return client.post(
        "/api/v1/videos",
        files={"file": ("v.mp4", io.BytesIO(b"\x00\x00\x00\x18ftypmp42data"), "video/mp4")},
    ).json()


@pytest.fixture
def fake_whisper(monkeypatch):
    segments = [
        {"start": 0.0, "end": 2.5, "text": "смотри главное", "avg_confidence": 0.9},
        {"start": 3.0, "end": 6.0, "text": "секрет в деталях", "avg_confidence": 0.8},
        {"start": 6.5, "end": 9.0, "text": "итак подведём итог", "avg_confidence": 0.85},
    ]
    info = {"device_used": "cpu", "compute_type": "int8", "model": "small",
            "duration": 9.0, "language": "ru"}

    def fake_extract(src, dst, **kwargs):
        from pathlib import Path

        Path(dst).write_bytes(b"RIFF fake wav")

    monkeypatch.setattr(
        "app.services.transcription.whisper_service.extract_audio_wav", fake_extract
    )
    monkeypatch.setattr(
        "app.services.transcription.whisper_service.transcribe_audio",
        lambda wav, **kw: (segments, info),
    )
    return segments


def test_transcribe_202_and_segments_saved(client, video, fake_whisper) -> None:
    response = client.post(f"/api/v1/videos/{video['id']}/transcribe")
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]

    job = client.get(f"/api/v1/jobs/{job_id}").json()
    assert job["status"] == "succeeded"
    assert job["result"]["segment_count"] == 3
    assert job["result"]["device_used"] == "cpu"

    transcript = client.get(f"/api/v1/videos/{video['id']}/transcript")
    assert transcript.status_code == 200
    body = transcript.json()
    assert body["total"] == 3
    assert body["items"][0]["text"] == "смотри главное"
    assert body["items"][0]["start"] == 0.0
    assert body["items"][0]["created_at"].endswith("Z")


def test_transcribe_idempotent_cached(client, video, fake_whisper) -> None:
    client.post(f"/api/v1/videos/{video['id']}/transcribe")
    second = client.post(f"/api/v1/videos/{video['id']}/transcribe")
    assert second.status_code == 202
    job = client.get(f"/api/v1/jobs/{second.json()['job_id']}").json()
    assert job["status"] == "succeeded"
    assert job["result"]["cached"] is True  # segments already present


def test_transcribe_video_not_found(client) -> None:
    response = client.post(f"/api/v1/videos/{uuid.uuid4()}/transcribe")
    assert response.status_code == 404


def test_transcribe_job_failed_when_whisper_unavailable(client, video, monkeypatch) -> None:
    from app.services.transcription.whisper_service import TranscribeError

    def fail_extract(src, dst, **kwargs):
        raise TranscribeError("ffmpeg_missing", "ffmpeg binary not found")

    monkeypatch.setattr(
        "app.services.transcription.whisper_service.extract_audio_wav", fail_extract
    )
    response = client.post(f"/api/v1/videos/{video['id']}/transcribe")
    assert response.status_code == 202
    job = client.get(f"/api/v1/jobs/{response.json()['job_id']}").json()
    assert job["status"] == "failed"
    assert "ffmpeg_missing" in job["error_message"]
    # API still answers normally for transcript (empty)
    assert client.get(f"/api/v1/videos/{video['id']}/transcript").json()["total"] == 0


def test_get_transcript_video_not_found(client) -> None:
    assert client.get(f"/api/v1/videos/{uuid.uuid4()}/transcript").status_code == 404
