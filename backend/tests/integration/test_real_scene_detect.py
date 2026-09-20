"""Real-binary scene detection test (marker real_services; RUN_REAL_INTEGRATION=1)."""
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
def two_scene_video() -> Path:
    ffmpeg = shutil.which(os.environ.get("FFMPEG_PATH", "ffmpeg"))
    if not ffmpeg:
        pytest.skip("ffmpeg binary not available")
    tmp = Path(tempfile.mkdtemp(prefix="scene-test-"))
    out = tmp / "twoscenes.mp4"
    # scene 1: noisy testsrc; scene 2: static color — hard visual cut at 4s
    subprocess.run(
        [
            ffmpeg, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=4:size=640x360:rate=25",
            "-f", "lavfi", "-i", "color=c=red:size=640x360:rate=25:duration=4",
            "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
            "-map", "[v]", "-pix_fmt", "yuv420p", "-c:v", "libx264", str(out),
        ],
        check=True, capture_output=True,
    )
    return out


def test_detect_scenes_finds_cut(two_scene_video) -> None:
    from app.services.transcription.scene_service import detect_scenes

    boundaries = detect_scenes(two_scene_video, threshold=0.3)
    assert boundaries, "expected at least one scene boundary at the 4s cut"
    # the hard cut is at ~4s
    assert any(abs(b - 4.0) < 1.0 for b in boundaries), f"boundaries: {boundaries}"


def test_uniform_fallback_when_no_scenes(two_scene_video) -> None:
    from app.services.transcription.scene_service import detect_scenes

    # absurdly high threshold => no boundaries => caller falls back
    boundaries = detect_scenes(two_scene_video, threshold=5.0)
    assert boundaries == []
