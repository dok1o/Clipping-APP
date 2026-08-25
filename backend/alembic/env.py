from __future__ import annotations

from pathlib import Path
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.infra.config import get_settings  # noqa: E402
from app.infra.database import Base  # noqa: E402
from app.infra import models  # noqa: F401, E402


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = context.config.get_section(context.config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_settings().database_url
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


def _has_alembic_context() -> bool:
    try:
        context.config
    except Exception:
        return False
    return True


if _has_alembic_context():
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()
