"""Canonical repository structure checks (master spec §5)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_canonical_dirs_exist() -> None:
    expected = [
        "AGENTS.md",
        "PROGRESS.md",
        "ARCHITECTURE.md",
        "CONTRACTS.md",
        "README.md",
        ".env.example",
        ".gitignore",
        "docs/MASTER_SPEC.md",
        "docs/KNOWLEDGE.md",
        "backend/pyproject.toml",
        "backend/alembic.ini",
        "backend/app/main.py",
        "backend/app/core/config.py",
        "backend/app/db",
        "backend/app/models",
        "backend/app/schemas",
        "backend/app/api/v1/router.py",
        "backend/app/services/ingest",
        "backend/app/services/clips",
        "backend/app/services/render",
        "backend/app/services/transcription",
        "backend/app/services/ai_clipping",
        "backend/app/services/text_gen",
        "backend/app/services/publish",
        "backend/app/services/analytics",
        "backend/app/services/ml",
        "backend/app/infra",
        "backend/app/workers",
        "backend/tests/unit",
        "backend/tests/api",
        "backend/tests/integration",
        "storage/.gitkeep",
        "scripts",
    ]
    missing = [str(p) for p in expected if not (ROOT / p).exists()]
    assert missing == [], f"missing canonical paths: {missing}"


def test_env_example_has_no_secrets() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    for secret_key in (
        "ENCRYPTION_KEY",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "YOUTUBE_CLIENT_SECRET",
        "YOUTUBE_REFRESH_TOKEN",
        "TIKTOK_CLIENT_SECRET",
        "TIKTOK_ACCESS_TOKEN",
    ):
        for line in text.splitlines():
            if line.startswith(f"{secret_key}="):
                value = line.split("=", 1)[1].strip()
                assert value == "", f"{secret_key} must be empty in .env.example, got: {value!r}"
