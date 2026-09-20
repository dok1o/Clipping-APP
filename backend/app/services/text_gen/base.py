"""Provider interface for local text generation (master spec §16).

Implementations: fake (tests/dev), local (ollama). Paid APIs are NOT part of
the system; llamacpp/transformers backends are honest NotImplemented stubs.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


class TextGenError(Exception):
    """Controlled generation failure (invalid JSON after retry, provider down, OOM)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@runtime_checkable
class TextGenProvider(Protocol):
    name: str

    def generate(self, prompt: str, platform: str, *, max_tokens: int, temperature: float,
                 timeout_sec: int) -> str:
        """Return the model output as a string (expected: JSON matching the schema).

        Raises TextGenError with a stable code (provider_unavailable, oom,
        generation_failed, not_implemented, ...). Callers never see tracebacks.
        """
        ...  # pragma: no cover
