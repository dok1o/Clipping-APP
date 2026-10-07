"""Runtime-audit t11.1: ONE database/config contract for every entry point.

- Settings env file is absolute (repo root .env, legacy backend/.env fallback)
  — independent of the current working directory;
- relative SQLite URLs are anchored at backend/ deterministically;
- DATABASE_URL from the real environment has the highest priority;
- alembic resolution (resolve_database_url) matches the app engine URL.
"""
import os
from pathlib import Path

from app.core.config import (
    BACKEND_DIR,
    REPO_ROOT,
    Settings,
    canonical_env_file,
    get_settings,
    normalize_database_url,
    resolve_database_url,
)


def test_canonical_env_file_is_absolute_and_repo_anchored() -> None:
    env_file = canonical_env_file()
    assert env_file.is_absolute()
    assert REPO_ROOT in env_file.parents or env_file.parent == REPO_ROOT
    # legacy fallback stays inside the repo as well
    assert str(env_file).startswith(str(REPO_ROOT))


def test_settings_model_config_uses_absolute_env_file() -> None:
    configured = Settings.model_config["env_file"]
    assert Path(configured).is_absolute()


def test_relative_sqlite_url_anchored_regardless_of_cwd(tmp_path: Path, monkeypatch) -> None:
    urls = set()
    for cwd in (tmp_path, REPO_ROOT, BACKEND_DIR, tmp_path / "nested"):
        cwd.mkdir(parents=True, exist_ok=True)
        monkeypatch.chdir(cwd)
        urls.add(Settings(_env_file=None, database_url="sqlite:///clipper-dev.db").database_url)
    assert urls == {
        f"sqlite:///{(BACKEND_DIR / 'clipper-dev.db').resolve().as_posix()}"
    }, f"cwd changed the database: {urls}"


def test_normalize_passthrough_cases() -> None:
    assert normalize_database_url("sqlite+pysqlite:////tmp/abs.db") == "sqlite+pysqlite:////tmp/abs.db"
    assert normalize_database_url("sqlite:///:memory:") == "sqlite:///:memory:"
    assert normalize_database_url("sqlite:///file:data.db?mode=memory&cache=shared") == (
        "sqlite:///file:data.db?mode=memory&cache=shared"
    )
    pg = "postgresql+psycopg://clipper:clipper@localhost:5432/clipper"
    assert normalize_database_url(pg) == pg
    # dot-relative form anchors too
    anchored = normalize_database_url("sqlite:///./x.db")
    assert anchored.endswith("/x.db") and anchored.startswith("sqlite:///")


def test_env_var_has_priority_over_env_file(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / "custom.env"
    env_file.write_text(
        "DATABASE_URL=sqlite:///from-file.db\nUPLOAD_MAX_MB=7\n", encoding="utf-8"
    )
    monkeypatch.setenv("DATABASE_URL", "sqlite:///from-env.db")
    s = Settings(_env_file=env_file)
    assert s.database_url == f"sqlite:///{(BACKEND_DIR / 'from-env.db').resolve().as_posix()}"
    assert s.upload_max_mb == 7  # non-conflicting keys still load from the file


def test_env_file_used_when_no_env_var(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    env_file = tmp_path / "custom.env"
    env_file.write_text("DATABASE_URL=sqlite:///from-file.db\n", encoding="utf-8")
    s = Settings(_env_file=env_file)
    assert s.database_url == f"sqlite:///{(BACKEND_DIR / 'from-file.db').resolve().as_posix()}"


def test_resolve_database_url_env_priority(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///env-var.db")
    assert resolve_database_url("sqlite:///ini.db") == (
        f"sqlite:///{(BACKEND_DIR / 'env-var.db').resolve().as_posix()}"
    )


def test_resolve_database_url_matches_settings_when_no_env_var(monkeypatch) -> None:
    """No DATABASE_URL in the environment -> alembic resolves EXACTLY what the
    app engine would use (canonical .env / Settings default)."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    try:
        expected = get_settings().database_url
        assert resolve_database_url("sqlite:///ini-fallback.db") == expected
    finally:
        get_settings.cache_clear()


def test_alembic_ini_fallback_only_without_app_settings(monkeypatch) -> None:
    """Isolated tooling scenario: Settings broken -> ini fallback survives."""
    import app.core.config as config_module

    monkeypatch.delenv("DATABASE_URL", raising=False)
    original = config_module.get_settings

    def _broken():
        raise RuntimeError("app package unavailable")

    monkeypatch.setattr(config_module, "get_settings", _broken)
    resolved = config_module.resolve_database_url("sqlite:///./ini.db")
    assert resolved == f"sqlite:///{(BACKEND_DIR / 'ini.db').resolve().as_posix()}"
    monkeypatch.setattr(config_module, "get_settings", original)
