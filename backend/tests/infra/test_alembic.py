from pathlib import Path

from alembic.config import Config

from app.infra.database import Base
from app.infra import models  # noqa: F401


BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
REVISION = BACKEND_DIR / "alembic" / "versions" / "20260825_0001_create_core_domain_tables.py"


def test_alembic_config_loads() -> None:
    config = Config(str(ALEMBIC_INI))

    assert config.get_main_option("script_location") == "alembic"


def test_alembic_target_metadata_has_core_tables() -> None:
    assert set(Base.metadata.tables) == {
        "videos",
        "clips",
        "jobs",
        "rendered_assets",
        "platform_accounts",
        "publications",
    }


def test_initial_revision_contains_core_create_table_operations() -> None:
    source = REVISION.read_text(encoding="utf-8")

    for table_name in (
        "videos",
        "clips",
        "jobs",
        "rendered_assets",
        "platform_accounts",
        "publications",
    ):
        assert f'op.create_table(\n        "{table_name}"' in source
