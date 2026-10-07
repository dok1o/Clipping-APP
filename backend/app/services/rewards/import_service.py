"""Content Rewards: campaign/brief import (CR-1, CONTRACTS ЧАСТЬ CR v2.1 §19).

Deterministic by (provider, external_campaign_id): re-import never duplicates
the campaign; identical terms/brief content reuses the version (content_hash),
changed content creates the next version. Import NEVER confirms terms and NEVER
activates briefs. Text/JSON/file inputs. No network calls to Content Rewards.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.reward_campaign import RewardCampaign, RewardCampaignStatus
from app.schemas.reward_campaign import (
    BriefInput,
    CampaignImportRequest,
    SourceAssetInput,
    TermsInput,
    TextImportRequest,
)
from app.services.rewards.campaign_service import (
    add_brief_version,
    add_terms_version,
)

BRIEF_FILE_EXTENSIONS = {".json", ".txt", ".md"}
_SAFE_RE = re.compile(r"[^a-z0-9._-]+")
MAX_SAFE_NAME_LEN = 80


def _sanitize_filename(name: str) -> str:
    """Local copy of the upload sanitization rule (kept domain-independent)."""
    base = Path(name or "").name.lower()
    cleaned = _SAFE_RE.sub("-", base).strip(".-") or "brief"
    return cleaned[:MAX_SAFE_NAME_LEN]


@dataclass
class ImportOutcome:
    campaign: RewardCampaign
    created: bool
    terms_version: CampaignTermsVersion | None = None
    terms_created: bool = False
    brief_version: CampaignBriefVersion | None = None
    brief_created: bool = False


def _find_campaign(db: Session, provider: str, external_campaign_id: str) -> RewardCampaign | None:
    return db.scalars(
        select(RewardCampaign).where(
            RewardCampaign.provider == provider,
            RewardCampaign.external_campaign_id == external_campaign_id,
        )
    ).first()


def import_campaign(db: Session, req: CampaignImportRequest) -> ImportOutcome:
    """Deterministic campaign import by (provider, external_campaign_id).

    - new (provider, external_campaign_id) -> campaign created (status from
      request, platforms/currency/imported_payload stored);
    - existing -> operational snapshot updated (name/status/platforms/budget/
      deadline/imported_payload/source_url; currency stays until submissions
      exist — reward_submissions arrive with migration 0009);
    - terms: identical content reuses the version, changed content adds the
      next version; NEVER confirmed here;
    - brief: same reuse rule; created as pending_approval; active pointer
      untouched; assets authorized=false.
    """
    campaign = _find_campaign(db, req.provider, req.external_campaign_id)
    created = False
    if campaign is None:
        campaign = RewardCampaign(
            provider=req.provider,
            external_campaign_id=req.external_campaign_id,
            name=req.name,
            brand_name=req.brand_name,
            source_url=req.source_url,
            status=req.status or RewardCampaignStatus.DRAFT,
            platforms=list(req.platforms) or None,
            currency=req.currency,
            budget_total=req.budget_total,
            budget_spent=req.budget_spent,
            deadline_at=req.deadline_at,
            imported_payload=req.imported_payload,
        )
        db.add(campaign)
        db.flush()
        created = True
    else:
        campaign.name = req.name
        campaign.brand_name = req.brand_name
        campaign.source_url = req.source_url
        campaign.status = req.status or campaign.status
        campaign.platforms = list(req.platforms) or None
        campaign.currency = req.currency
        campaign.budget_total = req.budget_total
        campaign.budget_spent = req.budget_spent
        campaign.deadline_at = req.deadline_at
        campaign.imported_payload = req.imported_payload
        db.flush()

    outcome = ImportOutcome(campaign=campaign, created=created)

    if req.terms is not None:
        outcome.terms_version, outcome.terms_created = add_terms_version(db, campaign.id, req.terms)

    brief = req.brief
    if isinstance(req, TextImportRequest):
        brief = BriefInput(
            raw_text=req.raw_text,
            source_url=req.brief_source_url,
            source_assets=req.brief_source_assets,
        )
    if brief is not None:
        outcome.brief_version, outcome.brief_created = add_brief_version(
            db,
            campaign.id,
            raw_text=brief.raw_text,
            structured_json=brief.structured_json,
            source_url=brief.source_url or req.source_url,
            source_assets=brief.source_assets,
        )

    db.commit()
    db.refresh(campaign)
    return outcome


def import_text(db: Session, req: TextImportRequest) -> ImportOutcome:
    """Text import: campaign fields + brief as plain raw_text."""
    return import_campaign(db, req)


def import_file(
    db: Session,
    *,
    filename: str,
    content: bytes,
    form_fields: dict[str, Any],
    storage=None,
) -> ImportOutcome:
    """File import: .json = full CampaignImportRequest; .txt/.md = brief text.

    Text brief files are persisted to S3 (key briefs/{campaign_id}/{sha256[:16]}-
    {safe_name}) only when a NEW brief version is created; re-importing the same
    content reuses the version and does not re-upload. .json imports carry the
    structure itself (kept in imported_payload), so no file is stored. No
    network calls to Content Rewards.
    """
    from pydantic import ValidationError

    ext = Path(filename or "").suffix.lower()
    if ext not in BRIEF_FILE_EXTENSIONS:
        raise AppError(
            415, "unsupported_media",
            "Import file must be .json, .txt or .md",
            fields={"filename": filename or ""},
        )
    is_text = ext in {".txt", ".md"}
    if is_text:
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AppError(422, "invalid_import_file", f"File is not valid UTF-8 text: {exc}") from exc
        try:
            req = TextImportRequest(raw_text=decoded, **form_fields)
        except ValidationError as exc:
            raise AppError(
                422, "invalid_import_file",
                f"Import file metadata is invalid: {exc.error_count()} field error(s)",
                fields={err["loc"][0] if err.get("loc") else "__root__": str(exc.errors()[0].get("msg", "invalid")) for err in exc.errors()},
            ) from exc
    else:
        try:
            parsed = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AppError(422, "invalid_import_file", f"File is not valid UTF-8 JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise AppError(422, "invalid_import_file", "JSON file must contain an object")
        try:
            req = CampaignImportRequest.model_validate(parsed)
        except ValidationError as exc:
            raise AppError(
                422, "invalid_import_file",
                f"JSON file does not match the campaign import schema: {exc.error_count()} field error(s)",
                fields={err["loc"][0] if err.get("loc") else "__root__": str(exc.errors()[0].get("msg", "invalid")) for err in exc.errors()},
            ) from exc

    outcome = import_campaign(db, req)
    if is_text and outcome.brief_created and storage is not None:
        digest = hashlib.sha256(content).hexdigest()[:16]
        key = f"briefs/{outcome.campaign.id}/{digest}-{_sanitize_filename(filename)}"
        storage.upload_fileobj(io.BytesIO(content), key, content_type="text/plain")
        outcome.brief_version.raw_file_key = key
        db.commit()
        db.refresh(outcome.brief_version)
    return outcome



