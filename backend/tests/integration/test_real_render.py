"""Real-binary end-to-end render test (marker real_services; RUN_REAL_INTEGRATION=1).

Requires a working ffmpeg (FFMPEG_PATH env or PATH). Generates a real synthetic
source, uploads it through the API, creates a clip, renders, verifies the asset.
"""
import io
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.real_services,
    pytest.mark.skipif(
        os.environ.get("RUN_REAL_INTEGRATION") != "1", reason="RUN_REAL_INTEGRATION != 1"
    ),
]


@pytest.fixture(scope="module")
def real_ffmpeg() -> str:
    ffmpeg = shutil.which(os.environ.get("FFMPEG_PATH", "ffmpeg"))
    if not ffmpeg:
        pytest.skip("ffmpeg binary not available")
    return ffmpeg


@pytest.fixture(scope="module")
def synthetic_video(real_ffmpeg: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "synth.mp4"
        subprocess.run(
            [
                real_ffmpeg, "-y",
                "-f", "lavfi", "-i", "testsrc=duration=6:size=1280x720:rate=30",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
                "-pix_fmt", "yuv420p", "-c:v", "libx264", "-c:a", "aac", str(out),
            ],
            check=True, capture_output=True,
        )
        return out.read_bytes()


def test_full_upload_clip_render_e2e(client, real_ffmpeg: str, synthetic_video: bytes) -> None:
    upload = client.post(
        "/api/v1/videos",
        files={"file": ("synth.mp4", io.BytesIO(synthetic_video), "video/mp4")},
    )
    assert upload.status_code == 201, upload.text
    video = upload.json()
    # duration is present only when a real ffprobe binary is available (spec: null otherwise)
    if shutil.which(os.environ.get("FFPROBE_PATH", "ffprobe")):
        assert video["duration_sec"] is not None and video["duration_sec"] > 5
    else:
        assert video["duration_sec"] is None and video["status"] == "ready"

    clip = client.post(
        f"/api/v1/videos/{video['id']}/clips/manual",
        json={"title": "e2e", "start_sec": 1.0, "end_sec": 6.0},
    )
    assert clip.status_code == 201
    clip_id = clip.json()["id"]

    render = client.post(f"/api/v1/clips/{clip_id}/render")
    assert render.status_code == 202
    job = client.get(f"/api/v1/jobs/{render.json()['id']}").json()
    assert job["status"] == "succeeded", job.get("error_message")

    asset = client.get(f"/api/v1/renders/{job['result']['asset_id']}").json()
    assert asset["status"] == "ready"
    assert (asset["width"], asset["height"]) == (1080, 1920)
    assert abs(asset["duration_sec"] - 5.0) < 0.5

    # download the rendered file through a presigned URL and verify it is a real mp4
    url = client.get(f"/api/v1/renders/{asset['id']}/download").json()["url"]
    import urllib.request

    with urllib.request.urlopen(url) as resp:  # noqa: S310 (presigned local URL)
        data = resp.read()
    assert len(data) > 10_000
    assert data[4:8] == b"ftyp"  # MP4 box structure
