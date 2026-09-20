"""Application settings (pydantic-settings). Single source of env parsing.

Env names and defaults mirror the master spec (see .env.example at repo root).
"""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- app ---
    app_env: Literal["dev", "test", "prod"] = "dev"
    app_version: str = "0.1.0"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    frontend_origin: str = "http://localhost:5173"
    cors_allow_origin_regex: str = ""  # additive: optional regex for dev previews

    # --- infrastructure ---
    database_url: str = "postgresql+psycopg://clipper:clipper@localhost:5432/clipper"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = ""  # empty => falls back to redis_url
    celery_task_always_eager: bool = False

    # --- S3 / MinIO ---
    s3_endpoint: str = "http://localhost:9000"
    s3_region: str = "us-east-1"
    s3_bucket: str = "clipper"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_use_ssl: bool = False

    # --- security ---
    encryption_key: str = ""

    # --- upload / clips ---
    upload_max_mb: int = 1024
    clip_min_sec: float = 5.0
    clip_max_sec: float = 180.0

    # --- ffmpeg ---
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    ffmpeg_timeout_sec: int = 600

    # --- whisper (Stage 3) ---
    whisper_model: str = "small"
    whisper_device: str = "auto"
    whisper_compute_type: str = "int8_float16"
    whisper_beam_size: int = 3

    # --- local LLM (Stage 2) ---
    llm_backend: Literal["fake", "ollama", "llamacpp", "transformers"] = "fake"
    llm_model_name: str = "Qwen2.5-7B-Instruct-Q4_K_M"
    llm_device: str = "auto"
    llm_max_tokens: int = 1024
    llm_temperature: float = 0.7
    llm_timeout_sec: int = 120

    # --- ai heuristics weights (Stage 3) ---
    ai_weights_speech: float = 0.3
    ai_weights_keywords: float = 0.25
    ai_weights_tempo: float = 0.15
    ai_weights_loudness: float = 0.15
    ai_weights_scene: float = 0.15

    # --- platforms (Stage 1.4+) ---
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_refresh_token: str = ""
    youtube_daily_limit: int = 10
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    tiktok_access_token: str = ""
    tiktok_daily_limit: int = 10
    publish_min_interval_sec: int = 300

    # --- ML (Stage 7) ---
    ml_min_samples: int = 80
    ml_active_version: str = ""
    ml_max_age_days: int = 30

    @property
    def effective_celery_broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def celery_eager_by_default(self) -> bool:
        """Eager mode: automatic in tests; env CELERY_TASK_ALWAYS_EAGER overrides (ADR-013)."""
        return self.app_env == "test" or self.celery_task_always_eager


@lru_cache
def get_settings() -> Settings:
    return Settings()
