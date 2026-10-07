#!/usr/bin/env python3
"""Real render verification through the CANONICAL renderer (runtime-audit t11.3).

Replaces the legacy verifier that imported the removed `app.video_effects.renderer`
module (audit defect 4.3). The only module allowed to run ffmpeg in this project is
`app.services.render.ffmpeg_runner` — this script uses exactly that.

Honest result codes: PASS / FAIL / SKIP (with the reason).
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.render.ffmpeg_runner import render_vertical  # noqa: E402


def discover_ffmpeg() -> str | None:
    """FFMPEG_PATH env/settings -> PATH -> imageio-ffmpeg bundled build."""
    import os

    from app.core.config import get_settings

    for candidate in (os.environ.get("FFMPEG_PATH"), get_settings().ffmpeg_path, "ffmpeg"):
        if candidate:
            found = shutil.which(candidate)
            if found:
                return found
    try:
        import imageio_ffmpeg

        candidate = imageio_ffmpeg.get_ffmpeg_exe()
        if candidate and Path(candidate).exists():
            return candidate
    except Exception:  # noqa: BLE001 - optional [media] extra not installed
        return None
    return None


def main() -> int:
    args = parse_args()
    ffmpeg = discover_ffmpeg()
    if not ffmpeg:
        print("[SKIP] ffmpeg binary not available (FFMPEG_PATH, PATH, imageio-ffmpeg).")
        print("       Install ffmpeg or: pip install -e '.[media]'")
        return 0

    from app.core.config import get_settings

    input_path = args.input_video.expanduser().resolve()
    if not input_path.is_file():
        print(f"[FAIL] input video does not exist: {input_path}")
        return 1
    if args.start < 0:
        print("[FAIL] start must be >= 0")
        return 1
    if args.end <= args.start:
        print("[FAIL] end must be greater than start")
        return 1

    keep_output = args.output is not None
    if keep_output:
        output_path = args.output.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_ctx = None
    else:
        tmp_ctx = tempfile.TemporaryDirectory(prefix="ai-clipper-render-verify-")
        output_path = Path(tmp_ctx.name) / "rendered.mp4"

    try:
        render_vertical(
            input_path,
            output_path,
            start_sec=args.start,
            duration_sec=args.end - args.start,
            ffmpeg_path=ffmpeg,
            timeout_sec=get_settings().ffmpeg_timeout_sec,
        )
        size = output_path.stat().st_size if output_path.exists() else 0
        if size <= 0:
            print(f"[FAIL] renderer produced no output ({output_path})")
            return 1
        print(f"[PASS] render_vertical {args.end - args.start:.2f}s via canonical ffmpeg_runner")
        print(f"       output: {output_path} ({size} bytes)")
        print(f"       ffmpeg: {ffmpeg}")
        print("\nRESULT: PASS")
        return 0
    except Exception as exc:  # noqa: BLE001 - verifier reports every failure honestly
        print(f"[FAIL] render failed: {type(exc).__name__}: {exc}")
        print("\nRESULT: FAIL")
        return 1
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()  # no temp files left behind


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify a real vertical render using the project's canonical ffmpeg_runner."
    )
    parser.add_argument("input_video", type=Path, help="Path to an existing source video file.")
    parser.add_argument("--start", type=float, default=0.0, help="Clip start timestamp in seconds.")
    parser.add_argument("--end", type=float, default=2.0, help="Clip end timestamp in seconds.")
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Optional output MP4 path (keeps the file; without it the render is temporary).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
