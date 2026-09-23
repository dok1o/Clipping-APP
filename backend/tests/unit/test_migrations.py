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


CR_TABLE_COLUMNS = {
    "reward_campaigns": {
        "id", "provider", "external_campaign_id", "name", "brand_name", "source_url",
        "status", "platforms", "currency", "budget_total", "budget_spent", "deadline_at",
        "imported_payload", "created_at", "updated_at",
        "current_terms_version_id", "active_brief_version_id",
    },
    "campaign_terms_versions": {
        "id", "campaign_id", "version", "content_hash", "payout_model",
        "cpm_rate", "per_post_amount", "retainer_amount", "retainer_cycle_days",
        "min_payout", "max_payout_per_clip", "creator_fee_percent",
        "fee_free_budget_threshold", "earnings_window_days", "payout_hold_days",
        "submission_deadline_minutes", "terms_source_url", "terms_checked_at",
        "confirmed_at", "created_at",
    },
    "campaign_brief_versions": {
        "id", "campaign_id", "version", "status", "raw_text", "raw_file_key",
        "structured_json", "source_url", "checklist", "parser_engine",
        "parser_confidence", "supersedes_id", "approved_at", "created_at",
    },
    "campaign_source_assets": {
        "id", "campaign_id", "brief_version_id", "kind", "storage_key", "external_url",
        "sha256", "title", "authorized", "authorization_note", "created_at",
    },
}
# v2.1 invariant: economic term fields must NOT be columns of reward_campaigns
CR_TERM_FIELDS = {
    "payout_model", "cpm_rate", "per_post_amount", "retainer_amount",
    "retainer_cycle_days", "min_payout", "max_payout_per_clip",
}


def test_upgrade_creates_cr_tables_exact_columns(tmp_path: Path) -> None:
    url = _set_url(tmp_path / "m1cr.db")
    command.upgrade(alembic_config(), "head")
    engine = create_engine(url)
    insp = inspect(engine)
    for table, expected in CR_TABLE_COLUMNS.items():
        cols = {c["name"] for c in insp.get_columns(table)}
        assert cols == expected, f"{table}: {cols ^ expected}"
    assert not (CR_TERM_FIELDS & CR_TABLE_COLUMNS["reward_campaigns"])
    engine.dispose()


ALL_DOMAIN_TABLES = {
    "videos", "clips", "jobs", "rendered_assets", "platform_accounts", "publications",  # 0001
    "transcript_segments", "clip_candidates",  # 0002
    "metrics",  # 0003
    "training_runs",  # 0004
    "reward_campaigns", "campaign_terms_versions",  # 0007 (CR-1)
    "campaign_brief_versions", "campaign_source_assets",
}
# 0006 alters jobs.type constraint only — no table changes; 0007 adds the CR
# campaign tables (verified as a set when stepping back one revision).
LATEST_REVISION_TABLES = {
    "reward_campaigns",
    "campaign_terms_versions",
    "campaign_brief_versions",
    "campaign_source_assets",
}


def test_downgrade_one_and_upgrade_again(tmp_path: Path) -> None:
    url = _set_url(tmp_path / "m2.db")
    command.upgrade(alembic_config(), "head")
    engine = create_engine(url)
    assert ALL_DOMAIN_TABLES <= set(inspect(engine).get_table_names())
    engine.dispose()

    # -1 drops only the latest revision's tables
    command.downgrade(alembic_config(), "-1")
    engine = create_engine(url)
    names = set(inspect(engine).get_table_names())
    assert not (LATEST_REVISION_TABLES & names)
    assert ALL_DOMAIN_TABLES - LATEST_REVISION_TABLES <= names
    engine.dispose()

    # base drops everything
    command.downgrade(alembic_config(), "base")
    engine = create_engine(url)
    assert not (ALL_DOMAIN_TABLES & set(inspect(engine).get_table_names()))
    engine.dispose()

    command.upgrade(alembic_config(), "head")
    engine = create_engine(url)
    assert ALL_DOMAIN_TABLES <= set(inspect(engine).get_table_names())
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
