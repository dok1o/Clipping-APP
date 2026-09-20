"""Model integrity: CHECK constraints, FK policies (ADR-FK), partial unique index."""
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.db import session as db_session
from app.models.clip import Clip, ClipStatus
from app.models.job import Job, JobType
from app.models.platform_account import PlatformAccount
from app.models.publication import Publication, PublicationStatus
from app.models.rendered_asset import RenderedAsset
from app.models.video import Video, VideoStatus


@pytest.fixture
def db(tmp_path: Path):
    from app.db.base import Base

    db_session.init_engine(f"sqlite+pysqlite:///{tmp_path / 'models.db'}")
    Base.metadata.create_all(db_session.get_engine())  # tests only (§9)
    session = db_session.session_factory()
    yield session
    session.close()
    db_session.reset_engine()


def _video(db, status=VideoStatus.READY, duration=None) -> Video:
    v = Video(
        original_filename="v.mp4",
        storage_key=f"videos/{uuid.uuid4()}/v.mp4",
        size_bytes=10,
        mime_type="video/mp4",
        duration_sec=duration,
        status=status,
    )
    db.add(v)
    db.commit()
    return v


def _clip(db, video_id, start=1.0, end=10.0) -> Clip:
    c = Clip(video_id=video_id, title="t", start_sec=start, end_sec=end, status=ClipStatus.DRAFT)
    db.add(c)
    db.commit()
    return c


def test_video_status_check_rejects_unknown(db) -> None:
    db.add(
        Video(
            original_filename="v.mp4",
            storage_key=f"videos/{uuid.uuid4()}/v.mp4",
            size_bytes=10,
            mime_type="video/mp4",
            status="weird",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_clip_time_order_constraint(db) -> None:
    v = _video(db)
    db.add(Clip(video_id=v.id, title="t", start_sec=5.0, end_sec=5.0))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_clip_negative_start_rejected(db) -> None:
    v = _video(db)
    db.add(Clip(video_id=v.id, title="t", start_sec=-1.0, end_sec=5.0))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_delete_video_with_clips_is_restricted(db) -> None:
    v = _video(db)
    _clip(db, v.id)
    with pytest.raises(IntegrityError):
        db.execute(delete(Video).where(Video.id == v.id))
        db.commit()
    db.rollback()


def test_delete_clip_cascades_rendered_assets(db) -> None:
    v = _video(db)
    c = _clip(db, v.id)
    asset = RenderedAsset(
        clip_id=c.id, storage_key=f"renders/{c.id}/{uuid.uuid4()}.mp4",
        size_bytes=5, duration_sec=9.0,
    )
    db.add(asset)
    db.commit()
    db.execute(delete(Clip).where(Clip.id == c.id))
    db.commit()
    db.expunge_all()  # drop identity map: verify the DB-level CASCADE via fresh SELECT
    from sqlalchemy import select

    assert db.execute(select(RenderedAsset).where(RenderedAsset.id == asset.id)).scalar_one_or_none() is None


def _account(db) -> PlatformAccount:
    acc = PlatformAccount(
        platform="youtube", external_account_id="channel-1",
        credentials_encrypted="gAAAA-encrypted", scopes=["youtube.upload"],
    )
    db.add(acc)
    db.commit()
    return acc


def test_publication_active_unique_per_clip_platform(db) -> None:
    v = _video(db)
    c = _clip(db, v.id)
    acc = _account(db)
    db.add(Publication(clip_id=c.id, platform_account_id=acc.id, platform="youtube",
                       idempotency_key="k1", status=PublicationStatus.PUBLISHED))
    db.commit()
    db.add(Publication(clip_id=c.id, platform_account_id=acc.id, platform="youtube",
                       idempotency_key="k2", status=PublicationStatus.DRAFT))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_publication_failed_allows_retry_record(db) -> None:
    v = _video(db)
    c = _clip(db, v.id)
    acc = _account(db)
    db.add(Publication(clip_id=c.id, platform_account_id=acc.id, platform="youtube",
                       idempotency_key="k1", status=PublicationStatus.FAILED))
    db.commit()
    db.add(Publication(clip_id=c.id, platform_account_id=acc.id, platform="youtube",
                       idempotency_key="k2", status=PublicationStatus.SCHEDULED))
    db.commit()  # failed publication does not block a new active one


def test_publication_idempotency_key_unique(db) -> None:
    v = _video(db)
    c1 = _clip(db, v.id)
    c2 = _clip(db, v.id)
    acc = _account(db)
    db.add(Publication(clip_id=c1.id, platform_account_id=acc.id, platform="tiktok", idempotency_key="same"))
    db.commit()
    db.add(Publication(clip_id=c2.id, platform_account_id=acc.id, platform="tiktok", idempotency_key="same"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_job_idempotency_key_unique(db) -> None:
    ref = uuid.uuid4()
    db.add(Job(job_type=JobType.RENDER, ref_type="clip", ref_id=ref, idempotency_key="dup"))
    db.commit()
    db.add(Job(job_type=JobType.RENDER, ref_type="clip", ref_id=ref, idempotency_key="dup"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_job_status_check(db) -> None:
    db.add(Job(job_type=JobType.RENDER, ref_type="clip", ref_id=uuid.uuid4(), status="broken"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_defaults_applied(db) -> None:
    v = _video(db)
    c = _clip(db, v.id)
    job = Job(job_type=JobType.RENDER, ref_type="clip", ref_id=c.id)
    db.add(job)
    db.commit()
    db.refresh(job)
    assert job.status == "queued"
    assert job.attempts == 0
    assert job.max_attempts == 3
    assert c.created_at is not None and v.created_at is not None
    assert isinstance(c.created_at, datetime)
    assert c.created_at.tzinfo is None  # sqlite naive; API layer converts to Z
