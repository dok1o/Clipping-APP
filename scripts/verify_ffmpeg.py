#!/usr/bin/env python3
"""Runtime verification of ffmpeg/ffprobe + the vertical render pipeline (§14).

Generates a synthetic video (testsrc + sine), probes it, renders a 1s vertical
clip through the project's ffmpeg_runner, then probes the OUTPUT and asserts:
1080x1920, H.264, AAC, yuv420p.

Honest result codes: PASS / FAIL / SKIP (with the reason).
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

RESULTS: list[tuple[str, str]] = []


def report(name: str, ok: bool, detail: str) -> bool:
    RESULTS.append((name, ("PASS" if ok else "FAIL") + " — " + detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return ok


def _probe_with_ffmpeg(ffmpeg: str, path: Path) -> dict | None:
    """Fallback metadata probe via `ffmpeg -i` stderr parsing (no ffprobe binary)."""
    import re

    result = subprocess.run([ffmpeg, "-i", str(path)], capture_output=True, text=True)
    text = result.stderr
    meta: dict = {"duration_sec": None, "width": None, "height": None, "video_codec": None,
                  "audio_codec": None, "pix_fmt": None}
    duration_match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", text)
    if duration_match:
        h, m, s = duration_match.groups()
        meta["duration_sec"] = int(h) * 3600 + int(m) * 60 + float(s)
    # ffmpeg stream line: "Video: h264 (High) (avc1 / ...), yuv420p(tv, progressive), 1080x1920 ..."
    video_match = re.search(
        r"Stream #0:\d+.*?: Video: (\w+)(?:\s*\([^)]*\))*, (\w+)(?:\s*\([^)]*\))*, (\d+)x(\d+)",
        text,
    )
    if video_match:
        meta["video_codec"] = video_match.group(1)
        meta["pix_fmt"] = video_match.group(2)
        meta["width"], meta["height"] = int(video_match.group(3)), int(video_match.group(4))
    audio_match = re.search(r"Stream #0:1.*?: Audio: (\w+)", text)
    if audio_match:
        meta["audio_codec"] = audio_match.group(1)
    return meta


def main() -> int:
    import os

    env_ffmpeg = os.environ.get("FFMPEG_PATH")
    env_ffprobe = os.environ.get("FFPROBE_PATH")
    ffmpeg = (shutil.which(env_ffmpeg) if env_ffmpeg else None) or shutil.which("ffmpeg")
    ffprobe = (shutil.which(env_ffprobe) if env_ffprobe else None) or shutil.which("ffprobe")
    if not ffmpeg:
        print("[SKIP] ffmpeg not available on this machine. Install ffmpeg and re-run.")
        print("       The pytest suite covers the runner with fakes; this script is the real-binary check.")
        return 0

    probe_mode = "ffprobe" if ffprobe else "ffmpeg -i (fallback parser)"

    def probe(path: Path) -> dict | None:
        if ffprobe:
            return probe_media(path, ffprobe_path=ffprobe)
        return _probe_with_ffmpeg(ffmpeg, path)

    version = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True).stdout.splitlines()[0]
    print(f"      {version}")
    print(f"      probe mode: {probe_mode}")

    from app.core.config import get_settings
    from app.services.render.ffmpeg_runner import probe_media, render_vertical

    ok_all = True
    with tempfile.TemporaryDirectory(prefix="verify-ffmpeg-") as tmp:
        tmp = Path(tmp)
        synth = tmp / "synth.mp4"
        gen = subprocess.run(
            [
                ffmpeg, "-y",
                "-f", "lavfi", "-i", "testsrc=duration=3:size=1280x720:rate=30",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                "-pix_fmt", "yuv420p", "-c:v", "libx264", "-c:a", "aac",
                str(synth),
            ],
            capture_output=True, text=True,
        )
        ok_all &= report("generate synthetic 1280x720 3s video", gen.returncode == 0,
                         gen.stderr.strip().splitlines()[-1] if gen.returncode else f"{synth.stat().st_size} bytes")

        meta = probe(synth)
        ok_all &= report(
            "ffprobe source metadata",
            bool(meta and meta["width"] == 1280 and meta["height"] == 720 and abs((meta["duration_sec"] or 0) - 3) < 0.5),
            f"{meta}",
        )

        out = tmp / "vertical.mp4"
        try:
            render_vertical(synth, out, start_sec=1.0, duration_sec=1.0, ffmpeg_path=ffmpeg, timeout_sec=get_settings().ffmpeg_timeout_sec)
            ok_all &= report("render_vertical 1s clip", out.exists() and out.stat().st_size > 0,
                             f"{out.stat().st_size if out.exists() else 0} bytes")
        except Exception as exc:  # noqa: BLE001
            ok_all &= report("render_vertical 1s clip", False, f"{type(exc).__name__}: {exc}")
            print("\nRESULT: FAIL")
            return 1

        out_meta = probe(out) or {}
        ok_all &= report("output is 1080x1920", out_meta.get("width") == 1080 and out_meta.get("height") == 1920,
                         f"{out_meta.get('width')}x{out_meta.get('height')}")
        codecs = {"video": out_meta.get("video_codec"), "audio": out_meta.get("audio_codec")}
        ok_all &= report("output codecs h264+aac", codecs.get("video") == "h264" and codecs.get("audio") == "aac", f"{codecs}")
        ok_all &= report("output pix_fmt yuv420p", out_meta.get("pix_fmt") == "yuv420p", f"{out_meta.get('pix_fmt')}")

        # faststart: moov atom before mdat
        data = out.read_bytes()
        ok_all &= report("faststart (moov before mdat)", b"moov" in data and b"mdat" in data
                         and data.find(b"moov") < data.find(b"mdat"),
                         f"moov@{data.find(b'moov')} mdat@{data.find(b'mdat')}")

    print("\nRESULT:", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
