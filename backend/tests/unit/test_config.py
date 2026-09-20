"""Settings parsing tests."""
from app.core.config import Settings


def test_defaults() -> None:
    s = Settings(_env_file=None)
    assert s.app_version == "0.1.0"
    assert s.upload_max_mb == 1024
    assert s.clip_min_sec == 5.0
    assert s.clip_max_sec == 180.0
    assert s.ffmpeg_timeout_sec == 600
    assert s.llm_backend == "fake"
    assert s.ai_weights_speech == 0.3


def test_env_override(monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_MAX_MB", "2")
    monkeypatch.setenv("S3_USE_SSL", "true")
    monkeypatch.setenv("LLM_BACKEND", "fake")
    s = Settings(_env_file=None)
    assert s.upload_max_mb == 2
    assert s.s3_use_ssl is True


def test_celery_broker_fallback() -> None:
    s = Settings(_env_file=None, celery_broker_url="", redis_url="redis://host:6379/0")
    assert s.effective_celery_broker_url == "redis://host:6379/0"
    s2 = Settings(_env_file=None, celery_broker_url="redis://other:1/0", redis_url="redis://host:6379/0")
    assert s2.effective_celery_broker_url == "redis://other:1/0"


def test_celery_eager_flag(monkeypatch) -> None:
    monkeypatch.delenv("CELERY_TASK_ALWAYS_EAGER", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    assert Settings(_env_file=None, app_env="test").celery_eager_by_default is True
    assert Settings(_env_file=None, app_env="dev").celery_eager_by_default is False
    assert (
        Settings(_env_file=None, app_env="dev", celery_task_always_eager=True).celery_eager_by_default
        is True
    )
