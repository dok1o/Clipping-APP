"""Readiness endpoint tests (CONTRACTS §4.1a, ADR-022, runtime-audit t11.2).

Acceptance from the audit:
- clean unmigrated DB -> NOT ready (503);
- migrated DB -> ready (200);
- stale revision -> NOT ready;
- secrets never leak into responses.
"""
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text


def _client_on_url(url: str) -> TestClient:
    from app.db import session as db_session
    from app.main import app

    db_session.init_engine(url)
    return TestClient(app)


def test_unmigrated_db_is_not_ready(tmp_path: Path) -> None:
    from app.db import session as db_session

    url = f"sqlite+pysqlite:///{tmp_path / 'empty.db'}"
    client = _client_on_url(url)
    try:
        response = client.get("/ready")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "not_ready"
        assert body["checks"]["schema"] in {"no_alembic_version", "missing_tables"}
        assert body["checks"]["db"] == "ok"  # connection alone is NOT readiness
    finally:
        db_session.reset_engine()


def test_migrated_db_is_ready(engine, s3_mock) -> None:
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/ready")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "ready"
        assert body["checks"]["schema"] == "ok"
        assert body["checks"]["db"] == "ok"
        assert body["checks"]["s3"] == "ok"  # moto dev backend
        # redis is an honest skip in tests and does not gate readiness
        assert body["checks"]["redis"] in {"ok", "skip"}


def test_stale_revision_is_not_ready(db_path: Path, s3_mock) -> None:
    from app.db import session as db_session

    url = f"sqlite+pysqlite:///{db_path}"
    # rewind the recorded revision without touching the schema
    db_session.init_engine(url)
    with db_session.get_engine().connect() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = '0001'"))
        conn.commit()
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/ready")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "not_ready"
        assert body["checks"]["schema"].startswith("stale_revision:")
    db_session.reset_engine()


def test_health_stays_liveness(engine) -> None:
    """/health keeps the §4.1 contract: always 200, no schema key."""
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert set(response.json()["checks"]) == {"db", "redis", "s3"}


def test_secrets_never_leak_into_responses(monkeypatch, engine, s3_mock) -> None:
    """A sentinel secret configured via env must not appear in any response."""
    from app.core.config import get_settings
    from app.main import app

    monkeypatch.setenv("S3_SECRET_KEY", "SENTINEL_SECRET_VALUE_42")
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            for url in ("/health", "/ready", "/api/v1/nonexistent", "/"):
                response = client.get(url)
                assert "SENTINEL_SECRET_VALUE_42" not in response.text, url
    finally:
        monkeypatch.delenv("S3_SECRET_KEY", raising=False)
        get_settings.cache_clear()
