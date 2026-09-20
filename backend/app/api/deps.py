"""Shared FastAPI dependencies."""
from app.core.config import get_settings  # noqa: F401 (re-export)
from app.db.session import get_db  # noqa: F401 (re-export)


def get_storage():
    from app.infra.s3 import S3Storage

    return S3Storage.from_settings(get_settings())
