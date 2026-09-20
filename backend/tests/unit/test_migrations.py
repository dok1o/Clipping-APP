"""Alembic migrations: upgrade/downgrade cycle + parity between migrations and model metadata."""
import os
from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, inspect

from app import models  # noqa: F401 (register metadata)
from app.db.base import Base
from tests.conftest import alembic_config

DOMAIN_TABLES = {"videos", "clips", "jobs", "rendered_assets", "platform_accounts", "publications"}


def _set_url(db_file: Path) -> str:
    url = f"sqlite+pysqlite:///{db_file}"
    os.environ["DATABASE_URL"] = url
    return url


def test_upgrade_head_creates_domain_tables(tmp_path: Path) -> None:
    url = _set_url(tmp_path / "m1.db")
    command.upgrade(alembic_config(), "head")
    engine = create_engine(url)
    insp = inspect(engine)
    assert DOMAIN_TABLES <= set(insp.get_table_names())  # + alembic_version
    cols = {c["name"] for c in insp.get_columns("videos")}
    assert cols == {
        "id", "original_filename", "storage_key", "size_bytes", "mime_type",
        "duration_sec", "width", "height", "status", "error_message", "created_at", "updated_at",
    }
    engine.dispose()


STAGE3_TABLES = {"transcript_segments", "clip_candidates"}


def test_downgrade_one_and_upgrade_again(tmp_path: Path) -> None:
    url = _set_url(tmp_path / "m2.db")
    command.upgrade(alembic_config(), "head")
    engine = create_engine(url)
    assert DOMAIN_TABLES | STAGE3_TABLES <= set(inspect(engine).get_table_names())
    engine.dispose()

    # -1 drops only the latest revision (Stage 3 tables)
    command.downgrade(alembic_config(), "-1")
    engine = create_engine(url)
    names = set(inspect(engine).get_table_names())
    assert not (STAGE3_TABLES & names)
    assert DOMAIN_TABLES <= names  # Stage 0/1 tables still there
    engine.dispose()

    # base drops everything
    command.downgrade(alembic_config(), "base")
    engine = create_engine(url)
    assert not (DOMAIN_TABLES | STAGE3_TABLES) & set(inspect(engine).get_table_names())
    engine.dispose()

    command.upgrade(alembic_config(), "head")
    engine = create_engine(url)
    assert DOMAIN_TABLES | STAGE3_TABLES <= set(inspect(engine).get_table_names())
    engine.dispose()


def _dump(engine) -> dict:
    insp = inspect(engine)
    out: dict[str, dict] = {}
    for table in sorted(insp.get_table_names()):
        if table == "alembic_version":
            continue
        out[table] = {
            "cols": tuple(
                (c["name"], str(c["type"]), c["nullable"]) for c in insp.get_columns(table)
            ),
            "uqs": tuple(
                sorted(tuple(sorted(u["column_names"])) for u in insp.get_unique_constraints(table))
            ),
            "idxs": tuple(
                sorted(
                    (i["name"], tuple(i["column_names"]), bool(i["unique"]))
                    for i in insp.get_indexes(table)
                    if not i["name"].startswith("sqlite_autoindex")
                )
            ),
            "fks": tuple(
                sorted(
                    (
                        tuple(fk["constrained_columns"]),
                        fk["referred_table"],
                        (fk.get("options") or {}).get("ondelete"),
                    )
                    for fk in insp.get_foreign_keys(table)
                )
            ),
            "cks": tuple(sorted(c["name"] for c in insp.get_check_constraints(table))),
        }
    return out


def test_migrations_match_model_metadata(tmp_path: Path) -> None:
    """Drift guard: schema from migrations == schema from Base.metadata (create_all allowed in tests only)."""
    url = _set_url(tmp_path / "mig.db")
    command.upgrade(alembic_config(), "head")
    migrated_engine = create_engine(url)
    models_engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'model.db'}")
    Base.metadata.create_all(models_engine)  # noqa: test-only parity check
    try:
        assert _dump(migrated_engine) == _dump(models_engine)
    finally:
        migrated_engine.dispose()
        models_engine.dispose()
