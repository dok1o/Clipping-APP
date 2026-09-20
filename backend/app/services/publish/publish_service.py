"""Publish orchestration: idempotency, encrypted credentials, status mapping.

Platform-agnostic: publishers are resolved through the registry (base.get_publisher).
YouTube support later = new adapter + registry entry, zero changes here (§15).
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.logging import get_logger
from app.core.security import decrypt_str, encrypt_str, mask_secret
from app.infra.s3 import S3Storage
from app.models.clip import Clip
from app.models.platform_account import PlatformAccount
from app.models.publication import Publication, PublicationStatus
from app.models.rendered_asset import RenderedAsset, RenderedAssetStatus
from app.services.publish.base import PlatformError, PublishRequest
from app.services.publish.tiktok import get_publisher

logger = get_logger(__name__)


def build_idempotency_key(clip_id: uuid.UUID, platform: str, asset_id: uuid.UUID, title: str) -> str:
    digest = hashlib.sha256(title.encode()).hexdigest()[:12]
    return f"{clip_id}:{platform}:{asset_id}:{digest}"


def get_clip_or_404(db: Session, clip_id: uuid.UUID) -> Clip:
    clip = db.get(Clip, clip_id)
    if clip is None:
        raise AppError(404, "clip_not_found", f"Clip {clip_id} not found")
    return clip


def get_asset_or_404(db: Session, clip_id: uuid.UUID) -> RenderedAsset:
    asset = db.scalars(
        select(RenderedAsset)
        .where(
            RenderedAsset.clip_id == clip_id,
            RenderedAsset.status == RenderedAssetStatus.READY,
        )
        .order_by(RenderedAsset.created_at.desc())
        .limit(1)
    ).first()
    if asset is None:
        raise AppError(404, "asset_not_found", f"Clip {clip_id} has no ready rendered asset")
    return asset


def get_account_or_404(db: Session, account_id: uuid.UUID) -> PlatformAccount:
    account = db.get(PlatformAccount, account_id)
    if account is None:
        raise AppError(404, "account_not_found", f"Platform account {account_id} not found")
    return account


def create_account(
    db: Session, *, platform: str, external_account_id: str, display_name: str | None,
    credentials: dict, scopes: list[str] | None = None,
) -> PlatformAccount:
    if platform not in ("youtube", "tiktok"):
        raise AppError(422, "validation_error", "platform must be youtube or tiktok")
    account = PlatformAccount(
        platform=platform,
        external_account_id=external_account_id,
        display_name=display_name,
        credentials_encrypted=encrypt_str(json.dumps(credentials)),
        scopes=scopes or [],
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def manual_publish(
    db: Session,
    storage: S3Storage,
    *,
    clip_id: uuid.UUID,
    platform: str,
    platform_account_id: uuid.UUID,
    title: str,
    description: str | None,
    privacy: str,
    scheduled_at: datetime | None,
) -> Publication:
    """CONTRACTS §4.11: 201 PublicationRead | 409 duplicate | 502 platform_error."""
    if platform not in ("youtube", "tiktok"):
        raise AppError(422, "validation_error", "platform must be youtube or tiktok")
    if privacy not in ("public", "unlisted", "private"):
        raise AppError(422, "validation_error", "privacy must be public, unlisted or private")

    clip = get_clip_or_404(db, clip_id)
    asset = get_asset_or_404(db, clip_id)
    account = get_account_or_404(db, platform_account_id)

    if account.platform != platform:
        raise AppError(
            422, "validation_error",
            f"Account {platform_account_id} belongs to {account.platform}, not {platform}",
        )
    if not account.is_active:
        raise AppError(422, "validation_error", "Platform account is inactive")

    idempotency_key = build_idempotency_key(clip_id, platform, asset.id, title)

    existing = db.scalar(select(Publication).where(Publication.idempotency_key == idempotency_key))
    if existing is not None:
        raise AppError(409, "duplicate_publication", "Publication with the same idempotency key exists")

    publication = Publication(
        clip_id=clip_id,
        rendered_asset_id=asset.id,
        platform_account_id=account.id,
        platform=platform,
        idempotency_key=idempotency_key,
        status=PublicationStatus.SCHEDULED if scheduled_at else PublicationStatus.UPLOADING,
        scheduled_at=scheduled_at,
        attempt_count=0,
        meta={"title": title, "description": description, "privacy": privacy},
    )
    db.add(publication)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        # race on the unique key => duplicate
        from sqlalchemy.exc import IntegrityError

        if isinstance(exc, IntegrityError):
            raise AppError(409, "duplicate_publication", "Publication with the same idempotency key exists") from exc
        raise

    if scheduled_at is not None:
        return publication  # Stage 5 worker picks it up from the schedule

    return execute_publication(db, storage, publication)


def execute_publication(db: Session, storage: S3Storage, publication: Publication) -> Publication:
    """Run the actual upload through the platform adapter (secret-free errors)."""
    publication.status = PublicationStatus.UPLOADING
    publication.attempt_count += 1
    db.commit()

    try:
        account = db.get(PlatformAccount, publication.platform_account_id)
        credentials = json.loads(decrypt_str(account.credentials_encrypted))
        publisher = get_publisher(publication.platform)
        meta = publication.meta or {}

        with tempfile.TemporaryDirectory(prefix="clipper-publish-") as tmp_dir:
            asset = db.get(RenderedAsset, publication.rendered_asset_id)
            local = Path(tmp_dir) / "asset.mp4"
            storage.download_to_file(asset.storage_key, local)
            request = PublishRequest(
                video_path=str(local),
                title=meta.get("title") or "",
                description=meta.get("description"),
                privacy=meta.get("privacy") or "public",
            )
            result = publisher.publish(request, credentials)

        publication.external_post_id = result.external_post_id
        publication.status = PublicationStatus.PUBLISHED
        publication.published_at = datetime.now(timezone.utc)
        publication.last_error = None
        db.commit()
    except PlatformError as exc:
        publication.status = PublicationStatus.FAILED
        publication.last_error = f"{exc.code}: {exc.message}"[:2000]
        db.commit()
        logger.warning("publication %s failed: %s", publication.id, publication.last_error)
        raise AppError(502, "platform_error", exc.message) from exc
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        publication.status = PublicationStatus.FAILED
        publication.last_error = f"internal_error: {exc}"[:2000]
        db.commit()
        raise AppError(502, "platform_error", "Publication failed") from exc

    db.refresh(publication)
    return publication


def list_publications(
    db: Session, clip_id: uuid.UUID | None, platform: str | None, limit: int, offset: int
) -> tuple[list[Publication], int]:
    from sqlalchemy import func

    query = select(Publication)
    count_query = select(func.count()).select_from(Publication)
    if clip_id is not None:
        query = query.where(Publication.clip_id == clip_id)
        count_query = count_query.where(Publication.clip_id == clip_id)
    if platform is not None:
        query = query.where(Publication.platform == platform)
        count_query = count_query.where(Publication.platform == platform)
    total = db.scalar(count_query) or 0
    rows = db.scalars(query.order_by(Publication.created_at.desc()).limit(limit).offset(offset))
    return list(rows), total
