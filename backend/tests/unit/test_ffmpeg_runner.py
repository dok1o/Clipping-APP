"""ffmpeg_runner unit tests (no real ffmpeg needed — fake binaries/scripts)."""
import stat
from pathlib import Path

import pytest

from app.services.render.ffmpeg_runner import (
    VERTICAL_FILTER,
    RenderError,
    build_render_args,
    render_vertical,
)


def test_vertical_filter_string() -> None:
    assert VERTICAL_FILTER == (
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
    )


def test_build_render_args_order_and_codecs() -> None:
    args = build_render_args(
        "/tmp/in.mp4", "/tmp/out.mp4", start_sec=12.5, duration_sec=29.5, ffmpeg_path="ffmpeg"
    )
    # fast seek BEFORE -i, precise trim AFTER -i
    assert args.index("-ss") < args.index("-i")
    assert args.index("-t") > args.index("-i")
    assert args[args.index("-ss") + 1] == "12.500"
    assert args[args.index("-t") + 1] == "29.500"
    assert args[args.index("-vf") + 1] == VERTICAL_FILTER
    assert args[args.index("-r") + 1] == "30"
    assert args[args.index("-c:v") + 1] == "libx264"
    assert args[args.index("-preset") + 1] == "veryfast"
    assert args[args.index("-crf") + 1] == "23"
    assert args[args.index("-c:a") + 1] == "aac"
    assert args[args.index("-b:a") + 1] == "128k"
    assert args[args.index("-pix_fmt") + 1] == "yuv420p"
    assert args[args.index("-movflags") + 1] == "+faststart"
    assert args[0] == "ffmpeg" and args[1] == "-y"
    # everything is list-args (no shell)
    assert all(isinstance(a, str) for a in args)


def _make_script(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def test_render_missing_binary(tmp_path) -> None:
    with pytest.raises(RenderError) as e:
        render_vertical(
            tmp_path / "in.mp4", tmp_path / "out.mp4",
            start_sec=0, duration_sec=5, ffmpeg_path=str(tmp_path / "no-such-ffmpeg"),
        )
    assert e.value.code == "ffmpeg_missing"


def test_render_timeout(tmp_path) -> None:
    fake = tmp_path / "ffmpeg-slow"
    _make_script(fake, "sleep 30")
    with pytest.raises(RenderError) as e:
        render_vertical(
            tmp_path / "in.mp4", tmp_path / "out.mp4",
            start_sec=0, duration_sec=5, ffmpeg_path=str(fake), timeout_sec=1,
        )
    assert e.value.code == "render_timeout"


def test_render_nonzero_exit_captures_stderr_tail(tmp_path) -> None:
    fake = tmp_path / "ffmpeg-fail"
    _make_script(fake, "echo 'boom error detail' >&2; exit 3")
    with pytest.raises(RenderError) as e:
        render_vertical(
            tmp_path / "in.mp4", tmp_path / "out.mp4",
            start_sec=0, duration_sec=5, ffmpeg_path=str(fake), timeout_sec=10,
        )
    assert e.value.code == "render_failed"
    assert "boom error detail" in e.value.stderr_tail


def test_render_empty_output_is_failure(tmp_path) -> None:
    fake = tmp_path / "ffmpeg-empty"
    _make_script(fake, "exit 0")  # succeeds but writes nothing
    with pytest.raises(RenderError) as e:
        render_vertical(
            tmp_path / "in.mp4", tmp_path / "out.mp4",
            start_sec=0, duration_sec=5, ffmpeg_path=str(fake), timeout_sec=10,
        )
    assert e.value.code == "render_failed"


def test_render_invalid_timestamps(tmp_path) -> None:
    with pytest.raises(RenderError) as e:
        render_vertical(
            tmp_path / "in.mp4", tmp_path / "out.mp4", start_sec=-1, duration_sec=5,
            ffmpeg_path="ffmpeg",
        )
    assert e.value.code == "invalid_timestamps"
    with pytest.raises(RenderError):
        render_vertical(
            tmp_path / "in.mp4", tmp_path / "out.mp4", start_sec=0, duration_sec=0,
            ffmpeg_path="ffmpeg",
        )


def test_stderr_tail_limit() -> None:
    from app.services.render.ffmpeg_runner import STDERR_TAIL_LIMIT, _tail

    huge = "x" * 10_000
    assert len(_tail(huge)) == STDERR_TAIL_LIMIT
    assert _tail(huge) == huge[-STDERR_TAIL_LIMIT:]
