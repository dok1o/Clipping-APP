"""Scene detection — ffmpeg select='gt(scene,THRESHOLD)' (ADR: zero new heavy deps;
PySceneDetect was rejected because it pulls OpenCV). Fallback: uniform windows.

The ONLY place scene detection runs; boundaries are computed during candidate
generation and stored in candidate features + API response (CONTRACTS §2.7 note).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_SCENE_THRESHOLD = 0.4
UNIFORM_WINDOW_SEC = 30.0

_SHOWINFO_RE = re.compile(r"pts_time:(\d+(?:\.\d+)?)")


def detect_scenes(
    video_path: str | Path, *, threshold: float = DEFAULT_SCENE_THRESHOLD
) -> list[float]:
    """Return scene boundary timestamps (seconds) via ffmpeg select+showinfo.

    Empty list when: binary missing, ffmpeg error, or no scene changes found.
    Never raises — caller falls back to uniform windows.
    """
    settings = get_settings()
    cmd = [
        settings.ffmpeg_path, "-y",
        "-i", str(video_path),
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ]
    try:
        completed = subprocess.run(  # noqa: S603 (list-args, no shell)
            cmd, capture_output=True, text=True, timeout=settings.ffmpeg_timeout_sec,
            check=False, shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("scene detection unavailable: %s", exc)
        return []
    if completed.returncode != 0:
        logger.warning("scene detection failed: %s", completed.stderr[-300:])
        return []
    return sorted({float(m) for m in _SHOWINFO_RE.findall(completed.stderr)})


def uniform_fallback_boundaries(duration_sec: float, window: float = UNIFORM_WINDOW_SEC) -> list[float]:
    """Fallback when the detector finds nothing: uniform window boundaries."""
    if duration_sec <= 0:
        return []
    return [round(t, 3) for t in _frange(window, duration_sec, window)]


def _frange(start: float, stop: float, step: float):
    value = start
    while value < stop:
        yield value
        value += step
