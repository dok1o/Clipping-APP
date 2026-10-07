"""Application settings (pydantic-settings). Single source of env parsing.

Env names and defaults mirror the master spec (see .env.example at repo root).

Runtime-audit t11.1 (2026-10-07): the env file and the SQLite path no longer
depend on the current working directory. The canonical env file is the
REPO ROOT .env (legacy backend/.env is honoured as a fallback), and relative
SQLite URLs are anchored at backend/ — so the app, Alembic, workers and
verifier scripts always open the SAME database, whatever the cwd is.
"""
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[3]

_SQLITE_PREFIXES = ("sqlite+pysqlite:///", "sqlite:///")


def canonical_env_file() -> Path:
    """One canonical env file: repo root .env if present, else legacy backend/.env."""
    root_env = REPO_ROOT / ".env"
    if root_env.exists():
        return root_env
    return BACKEND_DIR / ".env"


def normalize_database_url(url: str) -> str:
    """Anchor relative SQLite paths at BACKEND_DIR (cwd-independent, t11.1).

    sqlite:///clipper-dev.db -> sqlite:///{backend}/clipper-dev.db on every OS,
    for every entry point (app engine, alembic, workers, scripts). Absolute
    paths, :memory: and file: URIs pass through unchanged.
    """
    for prefix in _SQLITE_PREFIXES:
        if url.startswith(prefix):
            path_part = url[len(prefix):]
            if (
                not path_part
                or path_part.startswith("/")
                or path_part == ":memory:"
                or path_part.startswith("file:")
                or "mode=memory" in path_part
            ):
                return url
            anchored = (BACKEND_DIR / path_part).resolve().as_posix()
            return prefix + anchored
    return url


def resolve_database_url(ini_fallback: str | None = None) -> str:
    """Single URL resolution shared by the app engine and alembic/env.py (t11.1).

    Priority: DATABASE_URL env var > canonical .env (via Settings, incl. its
    defaults) > ini_fallback (alembic.ini, isolated tooling scenarios only).
    """
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return normalize_database_url(env_url)
    try:
        return get_settings().database_url  # already normalized by the validator
    except Exception:  # noqa: BLE001 - isolated tooling without the app package
        pass
    if ini_fallback:
        return normalize_database_url(ini_fallback)
    return normalize_database_url("sqlite:///./alembic-local.db")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=canonical_env_file(), env_file_encoding="utf-8", extra="ignore", case_sensitive=False
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

    @field_validator("database_url", mode="after")
    @classmethod
    def _anchor_sqlite_path(cls, value: str) -> str:
        return normalize_database_url(value)
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

    # --- ML rerank (Stage 7) ---
    ml_model_dir: str = "./models"  # joblib artifacts, NOT committed
    ml_min_training_rows: int = 30  # below this the dataset is too small to train
    ml_retrain_min_new_rows: int = 10  # self-training trigger
    ml_val_fraction: float = 0.25
    ml_rerank_enabled: bool = True
    ml_max_age_days: int = 30  # active model older than this -> prefer heuristic

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
