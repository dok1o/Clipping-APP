"""Renders API (CONTRACTS §4.7–§4.9)."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_settings, get_storage
from app.core.config import Settings
from app.core.errors import AppError
from app.infra.s3 import S3Storage
from app.models.rendered_asset import RenderedAsset
from app.schemas.rendered_asset import PresignedUrl, RenderedAssetRead

router = APIRouter(prefix="/renders", tags=["renders"])


@router.get("/{asset_id}", response_model=RenderedAssetRead)
def get_render(asset_id: uuid.UUID, db: Session = Depends(get_db)) -> RenderedAsset:
    asset = db.get(RenderedAsset, asset_id)
    if asset is None:
        raise AppError(404, "asset_not_found", f"Rendered asset {asset_id} not found")
    return asset


@router.get("/{asset_id}/download", response_model=PresignedUrl)
def download_render(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    storage: S3Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
) -> PresignedUrl:
    asset = db.get(RenderedAsset, asset_id)
    if asset is None:
        raise AppError(404, "asset_not_found", f"Rendered asset {asset_id} not found")
    url = storage.presigned_get(asset.storage_key, expires_sec=900)
    return PresignedUrl(url=url, expires_sec=900)


