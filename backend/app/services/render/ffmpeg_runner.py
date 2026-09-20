"""The ONLY module allowed to run ffmpeg/ffprobe (master spec §6).

Subprocess rules: list-args only, shell=False, timeouts, controlled errors,
stderr tail (<=2KB) captured for logs/jobs — never returned verbatim to API.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

STDERR_TAIL_LIMIT = 2048


class ProbeError(Exception):
    """ffprobe failed (binary missing, timeout, unparsable output, corrupt input)."""


class RenderError(Exception):
    """ffmpeg render failed. `code` is a stable machine-readable reason."""

    def __init__(self, code: str, message: str, stderr_tail: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.stderr_tail = stderr_tail[-STDERR_TAIL_LIMIT:]


def _tail(text: str) -> str:
    return (text or "")[-STDERR_TAIL_LIMIT:]


def probe_media(
    path: str | Path,
    *,
    ffprobe_path: str | None = None,
    timeout_sec: int | None = None,
) -> dict[str, Any] | None:
    """Probe media metadata with ffprobe.

    Returns {"duration_sec": float|None, "width": int|None, "height": int|None}
    or None when the binary is unavailable / probing fails (upload flow treats
    that as "duration unknown", CONTRACTS §4.2 — never fails the upload).
    """
    settings = get_settings()
    binary = ffprobe_path or settings.ffprobe_path
    timeout = timeout_sec or settings.ffmpeg_timeout_sec
    cmd = [
        binary,
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        completed = subprocess.run(  # noqa: S603 (list-args, no shell)
            cmd, capture_output=True, text=True, timeout=timeout, check=False, shell=False
        )
    except FileNotFoundError:
        logger.warning("ffprobe binary not found: %s — metadata will be null", binary)
        return None
    except subprocess.TimeoutExpired as exc:
        logger.warning("ffprobe timeout on %s: %s", path, exc)
        return None
    if completed.returncode != 0:
        logger.warning("ffprobe failed (%s): %s", path, _tail(completed.stderr))
        return None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        logger.warning("ffprobe returned unparsable output for %s", path)
        return None

    duration: float | None = None
    try:
        if "format" in payload and payload["format"].get("duration") not in (None, "N/A"):
            duration = float(payload["format"]["duration"])
    except (TypeError, ValueError):
        duration = None

    width: int | None = None
    height: int | None = None
    for stream in payload.get("streams", []):
        if stream.get("codec_type") == "video":
            width = stream.get("width")
            height = stream.get("height")
            break

    return {"duration_sec": duration, "width": width, "height": height}


# --- vertical render (CONTRACTS §5, master spec §13) ---

VERTICAL_FILTER = (
    "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
)
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
RENDER_FPS = 30  # fixed 30 fps (spec §13: -r 30)


def build_render_args(
    src: str | Path,
    dst: str | Path,
    *,
    start_sec: float,
    duration_sec: float,
    ffmpeg_path: str | None = None,
) -> list[str]:
    """Deterministic ffmpeg argument list.

    Fast seek (-ss BEFORE -i) + precise trim (-t after -i); fixed 30 fps;
    H.264 veryfast/crf23 + AAC 128k; yuv420p; faststart (CONTRACTS §5).
    """
    binary = ffmpeg_path or get_settings().ffmpeg_path
    return [
        binary,
        "-y",
        "-ss", f"{start_sec:.3f}",          # fast seek before input
        "-i", str(src),
        "-t", f"{duration_sec:.3f}",        # precise trim after input
        "-vf", VERTICAL_FILTER,
        "-r", str(RENDER_FPS),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(dst),
    ]


def render_vertical(
    src: str | Path,
    dst: str | Path,
    *,
    start_sec: float,
    duration_sec: float,
    ffmpeg_path: str | None = None,
    timeout_sec: int | None = None,
) -> None:
    """Render a vertical 1080x1920 clip. Raises RenderError with a stable code."""
    settings = get_settings()
    if start_sec < 0 or duration_sec <= 0:
        raise RenderError("invalid_timestamps", f"invalid start/duration: {start_sec}/{duration_sec}")

    cmd = build_render_args(
        src, dst, start_sec=start_sec, duration_sec=duration_sec, ffmpeg_path=ffmpeg_path
    )
    try:
        completed = subprocess.run(  # noqa: S603 (list-args, no shell)
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec or settings.ffmpeg_timeout_sec,
            check=False,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise RenderError("ffmpeg_missing", f"ffmpeg binary not found: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RenderError(
            "render_timeout",
            f"ffmpeg exceeded {settings.ffmpeg_timeout_sec}s",
            _tail((exc.stderr or b"").decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")),
        ) from exc

    if completed.returncode != 0:
        raise RenderError(
            "render_failed",
            f"ffmpeg exited with code {completed.returncode}",
            _tail(completed.stderr),
        )
    if not Path(dst).exists() or Path(dst).stat().st_size == 0:
        raise RenderError("render_failed", "ffmpeg produced no output file")


def extract_audio_wav(
    src: str | Path,
    dst: str | Path,
    *,
    ffmpeg_path: str | None = None,
    timeout_sec: int | None = None,
) -> None:
    """Extract 16kHz mono WAV (whisper input) — same binary-gateway rules."""
    settings = get_settings()
    binary = ffmpeg_path or settings.ffmpeg_path
    cmd = [
        binary, "-y",
        "-i", str(src),
        "-vn", "-ac", "1", "-ar", "16000",
        str(dst),
    ]
    try:
        completed = subprocess.run(  # noqa: S603 (list-args, no shell)
            cmd, capture_output=True, text=True,
            timeout=timeout_sec or settings.ffmpeg_timeout_sec, check=False, shell=False,
        )
    except FileNotFoundError as exc:
        raise RenderError("ffmpeg_missing", f"ffmpeg binary not found: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RenderError("render_timeout", "audio extraction timed out") from exc
    if completed.returncode != 0 or not Path(dst).exists():
        raise RenderError("audio_extract_failed", "failed to extract audio", _tail(completed.stderr))
