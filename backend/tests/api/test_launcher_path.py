"""Launcher migration path integration (runtime-audit §5.9, t11.1).

Simulates exactly what the launcher does — alembic upgrade head on a fresh
temporary DB, then serve the API against THE SAME URL — and proves the schema
is there (revision == head, videos table exists) and /api/v1/overview works.
"""
from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from tests.conftest import alembic_config as make_alembic_config


def test_launcher_migration_path_then_api_overview(tmp_path, monkeypatch, s3_mock) -> None:
    from app.db import session as db_session
    from app.main import app

    # 1) fresh TEMP database (never the user's DB)
    db_file = tmp_path / "launcher-path.db"
    url = f"sqlite+pysqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", url)

    # 2) launcher migration step — same resolution as env.py uses now
    cfg: AlembicConfig = make_alembic_config()
    command.upgrade(cfg, "head")

    # 3) schema is migrated: revision == head, required table exists
    engine = create_engine(url)
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    head = ScriptDirectory.from_config(cfg).get_current_head()
    with engine.connect() as conn:
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    engine.dispose()
    assert head is not None
    assert revision == head, f"alembic_version {revision} != head {head}"
    assert "videos" in tables
    assert "reward_campaigns" in tables  # 0007 (CR-1)

    # 4) API opens the SAME url -> overview must work (the audit's 500 case)
    db_session.init_engine(url)
    try:
        with TestClient(app) as client:
            ready = client.get("/ready")
            assert ready.status_code == 200, ready.text  # t11.2: launcher waits for THIS
            assert ready.json()["checks"]["schema"] == "ok"
            response = client.get("/api/v1/overview")
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["videos"] == {}  # empty DB: status counters dict
    finally:
        db_session.reset_engine()
