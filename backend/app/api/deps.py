"""Shared FastAPI dependencies."""
from app.core.config import get_settings  # noqa: F401 (re-export)
from app.db.session import get_db  # noqa: F401 (re-export)
