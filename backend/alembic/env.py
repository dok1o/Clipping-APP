"""Alembic environment. URL resolution: DATABASE_URL env var (test/dev/prod)."""
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from app import models  # noqa: E402,F401  (register metadata)
from app.db.base import Base  # noqa: E402

target_metadata = Base.metadata

# t11.1: URL resolution is SHARED with the app engine (app.core.config).
# Priority: DATABASE_URL env var > canonical .env (Settings) > alembic.ini
# (isolated tooling fallback). Relative sqlite paths are anchored at backend/.
from app.core.config import resolve_database_url

db_url = resolve_database_url(config.get_main_option("sqlalchemy.url"))
# set_main_option interpolates '%': escape percent signs (e.g. PG passwords).
config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))


def run_migrations_offline() -> None:
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
