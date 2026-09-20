"""Publications + platform accounts API (CONTRACTS §4.11)."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_storage
from app.infra.s3 import S3Storage
from app.schemas.publication import (
    ManualPublishCreate,
    PlatformAccountCreate,
    PlatformAccountPage,
    PlatformAccountRead,
    PublicationPage,
    PublicationRead,
)
from app.services.publish import publish_service

router = APIRouter(tags=["publications"])


@router.post("/publications/manual", status_code=201, response_model=PublicationRead)
def manual_publish(
    payload: ManualPublishCreate,
    db: Session = Depends(get_db),
    storage: S3Storage = Depends(get_storage),
):
    return publish_service.manual_publish(
        db,
        storage,
        clip_id=payload.clip_id,
        platform=payload.platform,
        platform_account_id=payload.platform_account_id,
        title=payload.title,
        description=payload.description,
        privacy=payload.privacy,
        scheduled_at=payload.scheduled_at,
    )


@router.get("/publications", response_model=PublicationPage)
def list_publications(
    clip_id: uuid.UUID | None = None,
    platform: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> PublicationPage:
    rows, total = publish_service.list_publications(db, clip_id, platform, limit, offset)
    return PublicationPage(
        items=[PublicationRead.model_validate(p) for p in rows], total=total
    )


@router.get("/publications/{publication_id}", response_model=PublicationRead)
def get_publication(publication_id: uuid.UUID, db: Session = Depends(get_db)):
    from app.core.errors import AppError
    from app.models.publication import Publication

    publication = db.get(Publication, publication_id)
    if publication is None:
        raise AppError(404, "publication_not_found", f"Publication {publication_id} not found")
    return publication


@router.post("/platform-accounts", status_code=201, response_model=PlatformAccountRead)
def create_platform_account(payload: PlatformAccountCreate, db: Session = Depends(get_db)):
    return publish_service.create_account(
        db,
        platform=payload.platform,
        external_account_id=payload.external_account_id,
        display_name=payload.display_name,
        credentials=payload.credentials,
        scopes=payload.scopes,
    )


@router.get("/platform-accounts", response_model=PlatformAccountPage)
def list_platform_accounts(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> PlatformAccountPage:
    from sqlalchemy import func, select

    from app.models.platform_account import PlatformAccount

    total = db.scalar(select(func.count()).select_from(PlatformAccount)) or 0
    rows = db.scalars(
        select(PlatformAccount).order_by(PlatformAccount.created_at.desc()).limit(limit).offset(offset)
    )
    return PlatformAccountPage(
        items=[PlatformAccountRead.model_validate(a) for a in rows], total=total
    )
