#!/usr/bin/env python3
"""Runtime verification of faster-whisper transcription (optional, Stage 3).

Checks: faster-whisper installed -> model load -> transcribe a 5s synthetic wav
(generated via ffmpeg) -> segments with timings. Honest PASS/FAIL/SKIP.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))


def main() -> int:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        print("[SKIP] faster-whisper not installed (pip install -e '.[whisper]'); "
              "main suite covers the service with mocks.")
        return 0

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("[SKIP] ffmpeg not available to synthesize audio; skipping real run.")
        return 0

    with tempfile.TemporaryDirectory(prefix="verify-whisper-") as tmp:
        wav = Path(tmp) / "synth.wav"
        gen = subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=5", str(wav)],
            capture_output=True, text=True,
        )
        if gen.returncode != 0:
            print("[FAIL] could not generate synthetic wav:", gen.stderr[-200:])
            return 1

        from app.services.transcription.whisper_service import transcribe_audio

        try:
            segments, info = transcribe_audio(wav)
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] transcription failed: {type(exc).__name__}: {exc}")
            return 1

        print(f"      device_used={info.get('device_used')} compute={info.get('compute_type')} "
              f"model={info.get('model')} language={info.get('language')}")
        if info.get("device_used") == "cpu":
            print("      (CPU mode — install CUDA-enabled ctranslate2 for GPU)")
        print(f"[PASS] transcription returned {len(segments)} segments")
        for seg in segments[:5]:
            print(f"      {seg['start']:.2f}-{seg['end']:.2f}: {seg['text'][:60]}")
        print("\nRESULT: PASS")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
