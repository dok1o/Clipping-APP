"""Text generation unit tests: fake provider, validation, limits, local OOM fallback."""
import json

import httpx
import pytest

from app.core.config import get_settings
from app.services.text_gen import text_service
from app.services.text_gen.base import TextGenError
from app.services.text_gen.fake_provider import FakeTextGenProvider
from app.services.text_gen.local_provider import LocalTextGenProvider
from app.services.text_gen.text_service import GeneratedTexts, apply_platform_limits, parse_and_validate


class _Clip:
    title = "Как монтировать клипы быстро"


def test_fake_provider_deterministic() -> None:
    provider = FakeTextGenProvider()
    prompt = text_service.build_prompt(_Clip(), "youtube", None, None)
    a = provider.generate(prompt, "youtube", max_tokens=100, temperature=0.1, timeout_sec=5)
    b = provider.generate(prompt, "youtube", max_tokens=100, temperature=0.1, timeout_sec=5)
    assert a == b
    texts = parse_and_validate(a)
    assert len(texts.titles) == 3
    assert texts.description
    assert 3 <= len(texts.hashtags) <= 8


def test_fake_provider_different_platform_different_output() -> None:
    provider = FakeTextGenProvider()
    p_yt = text_service.build_prompt(_Clip(), "youtube", None, None)
    p_tt = text_service.build_prompt(_Clip(), "tiktok", None, None)
    assert provider.generate(p_yt, "youtube", max_tokens=10, temperature=0.1, timeout_sec=5) != \
        provider.generate(p_tt, "tiktok", max_tokens=10, temperature=0.1, timeout_sec=5)


def test_parse_and_validate_accepts_markdown_fenced_json() -> None:
    raw = '```json\n{"titles": ["a"], "description": "d", "hashtags": ["#x"]}\n```'
    texts = parse_and_validate(raw)
    assert texts.titles == ["a"]


def test_parse_and_validate_rejects_garbage() -> None:
    with pytest.raises(Exception):
        parse_and_validate("not json at all")


def test_platform_limits_youtube() -> None:
    texts = GeneratedTexts(
        titles=["t" * 200], description="d" * 6000,
        hashtags=["#a" * 50 for _ in range(20)],
    )
    limited = apply_platform_limits(texts, "youtube")
    assert len(limited.titles[0]) == 100
    assert len(limited.description) == 5000
    assert sum(len(h) + 1 for h in limited.hashtags) <= 500
    assert len(limited.hashtags) <= 8


def test_platform_limits_tiktok() -> None:
    texts = GeneratedTexts(titles=["x" * 3000], description="d", hashtags=["plain", "#ok"])
    limited = apply_platform_limits(texts, "tiktok")
    assert len(limited.titles[0]) == 2200
    assert limited.hashtags[0] == "#plain"  # auto-hashed


def _ollama_handler(payloads_seen, *, oom_first=False, fail_status=None):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        payloads_seen.append(body)
        if fail_status:
            return httpx.Response(fail_status, text="server exploded")
        if oom_first and not body.get("options", {}).get("num_gpu") == 0:
            return httpx.Response(400, text="cuda out of memory while loading model")
        return httpx.Response(200, json={
            "message": {"content": '{"titles": ["a", "b", "c"], "description": "d", "hashtags": ["#x", "#y"]}'}
        })
    return httpx.MockTransport(handler)


def test_local_provider_ollama_happy_path(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_backend", "ollama")
    seen = []
    provider = LocalTextGenProvider(transport=_ollama_handler(seen))
    out = provider.generate("prompt", "tiktok", max_tokens=64, temperature=0.5, timeout_sec=10)
    texts = parse_and_validate(out)
    assert texts.titles == ["a", "b", "c"]
    assert seen[0]["model"] == get_settings().llm_model_name
    assert seen[0]["format"] == "json"
    assert provider.device_used == "gpu"


def test_local_provider_oom_falls_back_to_cpu(monkeypatch) -> None:
    """Spec §16: try GPU -> catch OOM -> retry on CPU (num_gpu=0); covered by unit mock."""
    monkeypatch.setattr(get_settings(), "llm_backend", "ollama")
    seen = []
    provider = LocalTextGenProvider(transport=_ollama_handler(seen, oom_first=True))
    out = provider.generate("prompt", "youtube", max_tokens=64, temperature=0.5, timeout_sec=10)
    assert parse_and_validate(out).titles == ["a", "b", "c"]
    assert len(seen) == 2
    assert seen[1]["options"]["num_gpu"] == 0  # CPU retry
    assert provider.device_used == "cpu"


def test_local_provider_unreachable() -> None:
    provider = LocalTextGenProvider(ollama_url="http://127.0.0.1:9", transport=None)
    with pytest.raises(TextGenError) as e:
        provider.generate("p", "youtube", max_tokens=10, temperature=0.1, timeout_sec=1)
    assert e.value.code == "provider_unavailable"


def test_local_provider_non_oom_http_error(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_backend", "ollama")
    seen = []
    provider = LocalTextGenProvider(transport=_ollama_handler(seen, fail_status=500))
    with pytest.raises(TextGenError) as e:
        provider.generate("p", "youtube", max_tokens=10, temperature=0.1, timeout_sec=5)
    assert e.value.code == "generation_failed"


@pytest.mark.parametrize("backend", ["llamacpp", "transformers"])
def test_stub_backends_are_honest_not_implemented(monkeypatch, backend) -> None:
    monkeypatch.setattr(get_settings(), "llm_backend", backend)
    provider = LocalTextGenProvider(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    with pytest.raises(TextGenError) as e:
        provider.generate("p", "youtube", max_tokens=10, temperature=0.1, timeout_sec=5)
    assert e.value.code == "not_implemented"
