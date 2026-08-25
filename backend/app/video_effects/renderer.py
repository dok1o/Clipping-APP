from __future__ import annotations

import subprocess
from pathlib import Path


TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
OUTPUT_FORMAT = "mp4"


class FfmpegRenderError(RuntimeError):
    pass


def build_vertical_render_args(input_path: Path, output_path: Path, start: float, duration: float) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-ss",
        _format_seconds(start),
        "-i",
        str(input_path),
        "-t",
        _format_seconds(duration),
        "-vf",
        f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=increase,crop={TARGET_WIDTH}:{TARGET_HEIGHT}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def render_vertical_clip(input_path: Path, output_path: Path, start: float, duration: float) -> None:
    args = build_vertical_render_args(input_path, output_path, start, duration)
    try:
        result = subprocess.run(args, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise FfmpegRenderError("ffmpeg could not be started") from exc
    if result.returncode != 0:
        raise FfmpegRenderError("ffmpeg render failed")


def _format_seconds(value: float) -> str:
    return f"{value:.3f}"
