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
