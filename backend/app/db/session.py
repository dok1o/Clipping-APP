"""Engine/session management.

init_engine(url)/reset_engine() exist for test isolation and eager Celery tasks
(ADR-004): everything (API dependencies and in-process eager tasks) shares the
same lazily-initialized engine + session factory.
"""
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker | None = None


def _enable_sqlite_fk_pragma(dbapi_conn, _record) -> None:  # pragma: no cover - dialect glue
    """SQLite enforces FKs only with this pragma (PG does it natively)."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def init_engine(url: str) -> Engine:
    global _engine, _session_factory
    _engine = create_engine(url, pool_pre_ping=True, future=True)
    if url.startswith("sqlite"):
        event.listen(_engine, "connect", _enable_sqlite_fk_pragma)
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    return _engine


def reset_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def get_engine() -> Engine:
    if _engine is None:
        init_engine(get_settings().database_url)
    return _engine


def get_session_factory() -> sessionmaker:
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory


def session_factory() -> Session:
    return get_session_factory()()


def get_db() -> Generator[Session, None, None]:
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
