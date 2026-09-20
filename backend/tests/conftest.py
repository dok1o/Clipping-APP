"""Test environment setup + shared fixtures.

Env vars are set BEFORE importing `app.*` so that settings/celery singletons
pick up the test configuration (APP_ENV=test, eager celery, fake S3, sqlite).
"""
import os
import shutil
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from cryptography.fernet import Fernet  # noqa: E402

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:////tmp/clipper-test-default.db")
os.environ.setdefault("S3_ENDPOINT", "http://127.0.0.1:9")
os.environ.setdefault("S3_ACCESS_KEY", "test-access-key")
os.environ.setdefault("S3_SECRET_KEY", "test-secret-key")
os.environ.setdefault("S3_BUCKET", "clipper-test")
os.environ.setdefault("S3_USE_SSL", "false")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "1")
os.environ.setdefault("LLM_BACKEND", "fake")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config as AlembicConfig  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from moto import mock_aws  # noqa: E402



def alembic_config() -> AlembicConfig:
    cfg = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


@pytest.fixture(scope="session")
def migrated_template(tmp_path_factory: Path) -> Path:
    """Run alembic migrations once on a template sqlite DB; tests copy the file."""
    template = tmp_path_factory.mktemp("template") / "template.db"
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{template}"
    command.upgrade(alembic_config(), "head")
    return template


@pytest.fixture
def db_path(tmp_path: Path, migrated_template: Path) -> Path:
    dst = tmp_path / "test.db"
    shutil.copyfile(migrated_template, dst)
    return dst


@pytest.fixture
def engine(db_path: Path):
    url = f"sqlite+pysqlite:///{db_path}"
    db_session.init_engine(url)
    yield db_session.get_engine()
    db_session.reset_engine()


@pytest.fixture
def db(engine):
    session = db_session.session_factory()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


@pytest.fixture
def s3_mock():
    with mock_aws():
        from app.infra.s3 import S3Storage

        storage = S3Storage(
            endpoint_url="http://test",
            region="us-east-1",
            bucket="clipper-test",
            access_key="test-access-key",
            secret_key="test-secret-key",
            use_ssl=False,
        )
        storage.ensure_bucket()
        yield storage


@pytest.fixture
def client():
    """Minimal API client (no DB/S3 isolation).

    Tests that touch the database or storage declare `engine` / `s3_mock`
    fixtures explicitly — they rebind the shared session factory / moto stack
    before the test body issues requests.
    """
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ---------- row factories ----------

@pytest.fixture
def make_video(db):
    from app.models.video import Video, VideoStatus

    def _make(**kwargs) -> Video:
        vid = kwargs.pop("id", uuid.uuid4())
        video = Video(
            id=vid,
            original_filename=kwargs.pop("original_filename", "test.mp4"),
            storage_key=kwargs.pop("storage_key", f"videos/{vid}/test.mp4"),
            size_bytes=kwargs.pop("size_bytes", 1024),
            mime_type=kwargs.pop("mime_type", "video/mp4"),
            duration_sec=kwargs.pop("duration_sec", None),
            status=kwargs.pop("status", VideoStatus.READY),
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        return video

    return _make


@pytest.fixture
def make_clip(db):
    from app.models.clip import Clip, ClipStatus

    def _make(video_id, **kwargs) -> Clip:
        clip = Clip(
            video_id=video_id,
            title=kwargs.pop("title", "Test clip"),
            start_sec=kwargs.pop("start_sec", 1.0),
            end_sec=kwargs.pop("end_sec", 10.0),
            status=kwargs.pop("status", ClipStatus.DRAFT),
        )
        db.add(clip)
        db.commit()
        db.refresh(clip)
        return clip

    return _make
