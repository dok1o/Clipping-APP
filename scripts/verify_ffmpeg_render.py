from __future__ import annotations

import argparse
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.video_effects.renderer import FfmpegRenderError, OUTPUT_FORMAT, render_vertical_clip


@dataclass(frozen=True)
class VerificationClipContext:
    input_path: Path
    start: float
    end: float
    output_path: Path

    @property
    def duration(self) -> float:
        return self.end - self.start


def main() -> int:
    args = parse_args()
    try:
        context = build_context(args)
        render_vertical_clip(
            input_path=context.input_path,
            output_path=context.output_path,
            start=context.start,
            duration=context.duration,
        )
    except (FfmpegRenderError, OSError, ValueError) as exc:
        print(f"render verification failed: {exc}", file=sys.stderr)
        return 1

    print(context.output_path)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local ffmpeg render verification using the project renderer.")
    parser.add_argument("input_video", type=Path, help="Path to an existing source video file.")
    parser.add_argument("--start", type=float, default=0.0, help="Clip start timestamp in seconds.")
    parser.add_argument("--end", type=float, default=2.0, help="Clip end timestamp in seconds.")
    parser.add_argument("--output", type=Path, default=None, help="Optional output MP4 path.")
    return parser.parse_args()


def build_context(args: argparse.Namespace) -> VerificationClipContext:
    input_path = args.input_video.expanduser().resolve()
    if not input_path.is_file():
        raise ValueError(f"input video does not exist: {input_path}")
    if args.start < 0:
        raise ValueError("start must be >= 0")
    if args.end <= args.start:
        raise ValueError("end must be greater than start")

    output_path = args.output
    if output_path is None:
        output_dir = Path(tempfile.mkdtemp(prefix="ai-clipper-render-verify-"))
        output_path = output_dir / f"rendered.{OUTPUT_FORMAT}"
    else:
        output_path = output_path.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

    return VerificationClipContext(
        input_path=input_path,
        start=args.start,
        end=args.end,
        output_path=output_path,
    )


if __name__ == "__main__":
    raise SystemExit(main())
