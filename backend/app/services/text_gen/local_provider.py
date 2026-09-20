"""Local LLM provider — the ONLY place a local model is loaded/called.

Real backend: ollama (external local runtime; VRAM/CPU managed by ollama itself,
Q4 quantized models fit 8GB VRAM per project constraints). CPU fallback on
GPU-OOM is implemented via a retry with num_gpu=0 (documented, unit-tested).

llamacpp / transformers backends are honest NotImplemented stubs (no heavy
dependencies in the required path).
"""
from __future__ import annotations

import json

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.text_gen.base import TextGenError

logger = get_logger(__name__)

DEFAULT_OLLAMA_URL = "http://localhost:11434"
OOM_MARKERS = ("out of memory", "cuda", "oom", "vram")


class LocalTextGenProvider:
    name = "local"

    def __init__(self, ollama_url: str = DEFAULT_OLLAMA_URL, transport=None) -> None:
        self.ollama_url = ollama_url.rstrip("/")
        self.transport = transport  # test injection (httpx.MockTransport)
        self.device_used: str | None = None

    def generate(self, prompt: str, platform: str, *, max_tokens: int, temperature: float,
                 timeout_sec: int) -> str:
        settings = get_settings()
        if settings.llm_backend == "llamacpp":
            raise TextGenError(
                "not_implemented",
                "LLM_BACKEND=llamacpp is not implemented; use 'ollama' or 'fake' "
                "(see ARCHITECTURE ADR-010)",
            )
        if settings.llm_backend == "transformers":
            raise TextGenError(
                "not_implemented",
                "LLM_BACKEND=transformers is not implemented; use 'ollama' or 'fake' "
                "(see ARCHITECTURE ADR-010)",
            )
        return self._generate_with_ollama(
            prompt, settings.llm_model_name, max_tokens, temperature, timeout_sec
        )

    def _generate_with_ollama(self, prompt: str, model: str, max_tokens: int,
                              temperature: float, timeout_sec: int) -> str:
        """Single ollama /api/chat call; on GPU-OOM retry once with num_gpu=0 (CPU)."""
        base_payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            text, used_gpu = self._chat(base_payload, timeout_sec)
            self.device_used = "gpu" if used_gpu else "cpu"
            return text
        except TextGenError as exc:
            if self._looks_like_oom(exc.message):
                logger.warning("LLM OOM on GPU (%s) — retrying on CPU (num_gpu=0)", exc.message)
                payload = dict(base_payload)
                payload["options"] = {**base_payload["options"], "num_gpu": 0}
                text, _ = self._chat(payload, timeout_sec)
                self.device_used = "cpu"  # CPU fallback after OOM (spec §16)
                return text
            raise

    def _chat(self, payload: dict, timeout_sec: int) -> tuple[str, bool]:
        try:
            with httpx.Client(timeout=timeout_sec, transport=self.transport) as client:
                response = client.post(f"{self.ollama_url}/api/chat", json=payload)
        except httpx.HTTPError as exc:
            raise TextGenError(
                "provider_unavailable",
                f"ollama unreachable at {self.ollama_url}: {type(exc).__name__}",
            ) from exc
        if response.status_code != 200:
            message = response.text[:300]
            if self._looks_like_oom(message):
                raise TextGenError("oom", f"ollama reported OOM: {message}")
            raise TextGenError("generation_failed", f"ollama HTTP {response.status_code}: {message}")
        try:
            body = response.json()
            content = body.get("message", {}).get("content", "")
        except ValueError as exc:
            raise TextGenError("generation_failed", "ollama returned non-JSON body") from exc
        if not content:
            raise TextGenError("generation_failed", "ollama returned empty content")
        return content, True

    @staticmethod
    def _looks_like_oom(message: str) -> bool:
        lowered = (message or "").lower()
        return any(marker in lowered for marker in OOM_MARKERS)
