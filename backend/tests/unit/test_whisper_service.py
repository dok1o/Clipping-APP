"""Whisper service unit tests: device resolution, fallback, mocked model."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.transcription.whisper_service import (
    TranscribeError,
    resolve_compute_type,
    resolve_device,
    transcribe_audio,
)


def test_resolve_device_auto() -> None:
    with patch(
        "app.services.transcription.whisper_service._cuda_available", return_value=True
    ):
        assert resolve_device("auto") == "cuda"
    with patch(
        "app.services.transcription.whisper_service._cuda_available", return_value=False
    ):
        assert resolve_device("auto") == "cpu"


def test_resolve_device_explicit() -> None:
    assert resolve_device("cuda") == "cuda"
    assert resolve_device("cpu") == "cpu"


def test_compute_type_cpu_fallback() -> None:
    assert resolve_compute_type("cpu", "int8_float16") == "int8"
    assert resolve_compute_type("cuda", "int8_float16") == "int8_float16"
    assert resolve_compute_type("cpu", "int8") == "int8"


def test_whisper_not_installed() -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("faster_whisper"):
            raise ImportError("nope")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(TranscribeError) as e:
            transcribe_audio("x.wav")
    assert e.value.code == "whisper_unavailable"


class _FakeModel:
    def __init__(self, model_name, device=None, compute_type=None):
        self.device = device
        self.compute_type = compute_type

    def transcribe(self, path, beam_size=3):
        seg1 = MagicMock(start=0.0, end=2.0, text=" привет мир ", avg_logprob=-0.1)
        seg2 = MagicMock(start=2.5, end=5.0, text="смотри главное", avg_logprob=-0.5)
        info = MagicMock(duration=5.0, language="ru")
        return iter([seg1, seg2]), info


def test_transcribe_happy_path_mocked() -> None:
    fake_module = MagicMock()
    fake_module.WhisperModel = _FakeModel
    with patch.dict("sys.modules", {"faster_whisper": fake_module}):
        segments, info = transcribe_audio("x.wav", device="cpu")
    assert segments[0]["text"] == "привет мир"
    assert segments[0]["start"] == 0.0
    assert segments[1]["end"] == 5.0
    assert 0 < segments[0]["avg_confidence"] <= 1
    assert info["device_used"] == "cpu"
    assert info["compute_type"] == "int8"  # cpu fallback of int8_float16


@pytest.mark.parametrize(
    "cuda_error",
    ["CUDA out of memory", "Library cublas64_12.dll is not found or cannot be loaded"],
)
def test_transcribe_cuda_failure_falls_back_to_cpu(cuda_error: str) -> None:
    """Spec §17: CUDA runtime failures use CPU/int8 and record the actual device."""
    attempts = []

    class OomThenOk:
        def __init__(self, model_name, device=None, compute_type=None):
            attempts.append((device, compute_type))
            if device == "cuda":
                raise RuntimeError(cuda_error)

        def transcribe(self, path, beam_size=3):
            seg = MagicMock(start=0.0, end=1.0, text="ok", avg_logprob=None)
            info = MagicMock(duration=1.0, language="ru")
            return iter([seg]), info

    fake_module = MagicMock()
    fake_module.WhisperModel = OomThenOk
    with patch.dict("sys.modules", {"faster_whisper": fake_module}):
        segments, info = transcribe_audio("x.wav", device="cuda")
    assert attempts[0] == ("cuda", "int8_float16")
    assert attempts[1] == ("cpu", "int8")  # fallback
    assert info["device_used"] == "cpu"
    assert info["compute_type"] == "int8"
    assert segments[0]["text"] == "ok"
