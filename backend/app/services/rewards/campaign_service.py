"""Content Rewards: campaign import + immutable versioned terms + brief versions.

CR-1 scope (CONTRACTS ЧАСТЬ CR v2.1):
- import campaign from JSON/text/file input, deterministic by
  (provider, external_campaign_id) — no duplicates;
- economic terms live ONLY in `campaign_terms_versions` (INSERT-only rows,
  content_hash = sha256 of canonical JSON; identical content reuses the
  existing version, changed content creates the next version);
- import NEVER confirms terms and NEVER activates a brief (no auto-activation:
  briefs land as pending_approval; confirmation/approval are separate explicit
  user actions);
- source assets are created with authorized=false;
- no network calls to Content Rewards providers (manual-first, ADR-018).
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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.rewards import (
    CampaignBriefVersion,
    CampaignSourceAsset,
    CampaignTermsStatus,
    CampaignTermsVersion,
    PayoutModel,
    RewardCampaign,
    RewardCampaignStatus,
)
from app.schemas.rewards import (
    BriefInput,
    CampaignImportRequest,
    SourceAssetInput,
    TermsInput,
    TextImportRequest,
    utcnow,
)
from app.services.rewards.money import terms_content_hash

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


# --- terms validation (CR v2.1 payout_model field matrix) ---------------------

def validate_terms(t: TermsInput) -> None:
    """Service-level validation of the payout_model field matrix + bounds.

    Mirrors the DB CHECKs (payout_model_fields / payout_bounds / ...) so the
    client gets a 422 with per-field reasons instead of an IntegrityError.
    """
    fields: dict[str, str] = {}

    def _require(name: str, value: Any) -> None:
        if value is None:
            fields[name] = "required for this payout_model"

    def _forbid(name: str, value: Any) -> None:
        if value is not None:
            fields[name] = "must be NULL for this payout_model"

    if t.payout_model == PayoutModel.CPM:
        _require("cpm_rate", t.cpm_rate)
        _forbid("per_post_amount", t.per_post_amount)
        _forbid("retainer_amount", t.retainer_amount)
        _forbid("retainer_cycle_days", t.retainer_cycle_days)
    elif t.payout_model == PayoutModel.PER_POST:
        _require("per_post_amount", t.per_post_amount)
        _forbid("cpm_rate", t.cpm_rate)
        _forbid("retainer_amount", t.retainer_amount)
        _forbid("retainer_cycle_days", t.retainer_cycle_days)
    else:  # retainer
        _require("retainer_amount", t.retainer_amount)
        _require("retainer_cycle_days", t.retainer_cycle_days)
        _forbid("cpm_rate", t.cpm_rate)
        _forbid("per_post_amount", t.per_post_amount)

    if t.max_payout_per_clip is not None and t.min_payout is not None:
        if t.max_payout_per_clip < t.min_payout:
            fields["max_payout_per_clip"] = "cannot be less than min_payout"
    if t.min_payout is not None and t.min_payout < 0:
        fields["min_payout"] = "must be >= 0"
    if t.max_payout_per_clip is not None and t.max_payout_per_clip <= 0:
        fields["max_payout_per_clip"] = "must be > 0"
    if not (Decimal(0) <= t.creator_fee_percent <= Decimal(100)):
        fields["creator_fee_percent"] = "must be between 0 and 100"
    if t.fee_free_budget_threshold < 0:
        fields["fee_free_budget_threshold"] = "must be >= 0"
    if t.cpm_rate is not None and t.cpm_rate <= 0:
        fields["cpm_rate"] = "must be > 0"
    if t.per_post_amount is not None and t.per_post_amount <= 0:
        fields["per_post_amount"] = "must be > 0"
    if t.retainer_amount is not None and t.retainer_amount <= 0:
        fields["retainer_amount"] = "must be > 0"

    if fields:
        raise AppError(
            422,
            "invalid_campaign_terms",
            "Campaign terms violate the payout_model contract",
            fields=fields,
        )


def _terms_hash_payload(t: TermsInput) -> dict[str, Any]:
    """Canonical JSON payload of terms for content_hash (money as plain numbers)."""
    return {
        "payout_model": t.payout_model,
        "cpm_rate": None if t.cpm_rate is None else format(t.cpm_rate, "f"),
        "per_post_amount": None if t.per_post_amount is None else format(t.per_post_amount, "f"),
        "retainer_amount": None if t.retainer_amount is None else format(t.retainer_amount, "f"),
        "retainer_cycle_days": t.retainer_cycle_days,
        "min_payout": None if t.min_payout is None else format(t.min_payout, "f"),
        "max_payout_per_clip": None if t.max_payout_per_clip is None else format(
            t.max_payout_per_clip, "f"
        ),
        "creator_fee_percent": format(t.creator_fee_percent, "f"),
        "fee_free_budget_threshold": format(t.fee_free_budget_threshold, "f"),
        "earnings_window_days": t.earnings_window_days,
        "payout_hold_days": t.payout_hold_days,
        "submission_deadline_minutes": t.submission_deadline_minutes,
    }


# --- campaign lookup -----------------------------------------------------------

def get_campaign_or_404(db: Session, campaign_id: UUID) -> RewardCampaign:
    campaign = db.get(RewardCampaign, campaign_id)
    if campaign is None:
        raise AppError(404, "campaign_not_found", f"Campaign {campaign_id} not found")
    return campaign


def _find_campaign(db: Session, provider: str, external_campaign_id: str) -> RewardCampaign | None:
    return db.scalars(
        select(RewardCampaign).where(
            RewardCampaign.provider == provider,
            RewardCampaign.external_campaign_id == external_campaign_id,
        )
    ).first()


def _last_terms_version(db: Session, campaign_id: UUID) -> CampaignTermsVersion | None:
    return db.scalars(
        select(CampaignTermsVersion)
        .where(CampaignTermsVersion.campaign_id == campaign_id)
        .order_by(CampaignTermsVersion.version.desc())
        .limit(1)
    ).first()


def _last_brief_version(db: Session, campaign_id: UUID) -> CampaignBriefVersion | None:
    return db.scalars(
        select(CampaignBriefVersion)
        .where(CampaignBriefVersion.campaign_id == campaign_id)
        .order_by(CampaignBriefVersion.version.desc())
        .limit(1)
    ).first()


# --- terms versions (immutable, INSERT-only) ------------------------------------

def _next_version(db: Session, model, campaign_id: UUID) -> int:
    max_v = db.scalar(
        select(func.max(model.version)).where(model.campaign_id == campaign_id)
    )
    return (max_v or 0) + 1


def add_terms_version(
    db: Session, campaign_id: UUID, t: TermsInput
) -> tuple[CampaignTermsVersion, bool]:
    """Create (or reuse) the terms version for the given content.

    Returns (version, created). Identical content_hash reuses the latest
    version — changing terms means NEW content, which becomes version N+1.
    The version is created UNCONFIRMED; confirmation is a separate action.
    """
    validate_terms(t)
    campaign = get_campaign_or_404(db, campaign_id)
    content_hash = terms_content_hash(_terms_hash_payload(t))
    last = _last_terms_version(db, campaign.id)
    if last is not None and last.content_hash == content_hash:
        return last, False
    version = CampaignTermsVersion(
        campaign_id=campaign.id,
        version=_next_version(db, CampaignTermsVersion, campaign.id),
        content_hash=content_hash,
        payout_model=t.payout_model,
        cpm_rate=t.cpm_rate,
        per_post_amount=t.per_post_amount,
        retainer_amount=t.retainer_amount,
        retainer_cycle_days=t.retainer_cycle_days,
        min_payout=t.min_payout,
        max_payout_per_clip=t.max_payout_per_clip,
        creator_fee_percent=t.creator_fee_percent,
        fee_free_budget_threshold=t.fee_free_budget_threshold,
        earnings_window_days=t.earnings_window_days,
        payout_hold_days=t.payout_hold_days,
        submission_deadline_minutes=t.submission_deadline_minutes,
        terms_source_url=t.terms_source_url,
        terms_checked_at=t.terms_checked_at or utcnow(),
    )
    db.add(version)
    db.flush()
    return version, True


def confirm_terms(
    db: Session, campaign_id: UUID, version_id: UUID
) -> tuple[RewardCampaign, CampaignTermsVersion]:
    """Explicit user confirmation: sets confirmed_at + current_terms_version_id.

    Idempotent for an already-confirmed version. The pointer moves ONLY here.
    """
    campaign = get_campaign_or_404(db, campaign_id)
    version = db.get(CampaignTermsVersion, version_id)
    if version is None or version.campaign_id != campaign.id:
        raise AppError(
            404, "terms_version_not_found", f"Terms version {version_id} not found for campaign"
        )
    if version.confirmed_at is None:
        version.confirmed_at = utcnow()
    campaign.current_terms_version_id = version.id
    db.flush()
    return campaign, version


def list_terms_versions(db: Session, campaign_id: UUID) -> list[CampaignTermsVersion]:
    get_campaign_or_404(db, campaign_id)
    return list(
        db.scalars(
            select(CampaignTermsVersion)
            .where(CampaignTermsVersion.campaign_id == campaign_id)
            .order_by(CampaignTermsVersion.version.asc())
        )
    )


# --- brief versions (pending_approval, no auto-activation) ----------------------

def _brief_identity(raw_text: str | None, structured_json: dict | None, source_url: str) -> str:
    """Content identity of a brief (raw_file_key excluded: it is a derived
    storage location of the same content and would break idempotent reuse)."""
    return terms_content_hash(
        {"raw_text": raw_text, "structured_json": structured_json, "source_url": source_url}
    )


def add_brief_version(
    db: Session,
    campaign_id: UUID,
    *,
    raw_text: str | None = None,
    raw_file_key: str | None = None,
    structured_json: dict[str, Any] | None = None,
    source_url: str,
    source_assets: list[SourceAssetInput] | None = None,
    parser_engine: str = "manual",
) -> tuple[CampaignBriefVersion, bool]:
    """Create (or reuse) a brief version with status=pending_approval.

    The campaign's active_brief_version_id is NOT touched here — approval is a
    separate explicit user action (decide_brief). Source assets attached to a
    NEW version are created with authorized=False.
    """
    if raw_text is None and raw_file_key is None and structured_json is None:
        raise AppError(
            422, "invalid_brief", "Brief requires raw_text, raw_file_key or structured_json"
        )
    campaign = get_campaign_or_404(db, campaign_id)
    identity = _brief_identity(raw_text, structured_json, source_url)
    last = _last_brief_version(db, campaign.id)
    if last is not None and _brief_identity(
        last.raw_text, last.structured_json, last.source_url
    ) == identity:
        return last, False
    version = CampaignBriefVersion(
        campaign_id=campaign.id,
        version=_next_version(db, CampaignBriefVersion, campaign.id),
        status=CampaignTermsStatus.PENDING_APPROVAL,
        raw_text=raw_text,
        raw_file_key=raw_file_key,
        structured_json=structured_json,
        source_url=source_url or campaign.source_url,
        parser_engine=parser_engine,
    )
    db.add(version)
    db.flush()
    for asset in source_assets or []:
        if asset.external_url is None and asset.storage_key is None:
            raise AppError(
                422, "invalid_source_asset",
                f"Source asset {asset.title!r} requires external_url or storage_key",
            )
        db.add(
            CampaignSourceAsset(
                campaign_id=campaign.id,
                brief_version_id=version.id,
                kind=asset.kind,
                storage_key=asset.storage_key,
                external_url=asset.external_url,
                sha256=asset.sha256,
                title=asset.title,
                authorized=False,  # explicit user authorization required, never default-on
            )
        )
    db.flush()
    return version, True


def decide_brief(
    db: Session, campaign_id: UUID, version_id: UUID, action: str
) -> CampaignBriefVersion:
    """Explicit user approve/reject of a pending brief version.

    approve -> status=approved, approved_at=now, previous approved version
    becomes superseded, campaign.active_brief_version_id points to it.
    reject -> status=rejected. Only pending_approval (or the same approved
    version, idempotently) may transition.
    """
    campaign = get_campaign_or_404(db, campaign_id)
    version = db.get(CampaignBriefVersion, version_id)
    if version is None or version.campaign_id != campaign.id:
        raise AppError(
            404, "brief_version_not_found", f"Brief version {version_id} not found for campaign"
        )
    if action == "approve":
        if version.status == CampaignTermsStatus.APPROVED:
            return version  # idempotent re-approve
        if version.status != CampaignTermsStatus.PENDING_APPROVAL:
            raise AppError(
                409, "invalid_brief_state",
                f"Cannot approve brief in status {version.status}",
            )
        previous = db.scalars(
            select(CampaignBriefVersion).where(
                CampaignBriefVersion.campaign_id == campaign.id,
                CampaignBriefVersion.status == CampaignTermsStatus.APPROVED,
                CampaignBriefVersion.id != version.id,
            )
        )
        for prev in previous:
            prev.status = CampaignTermsStatus.SUPERSEDED
        version.status = CampaignTermsStatus.APPROVED
        version.approved_at = utcnow()
        campaign.active_brief_version_id = version.id
    elif action == "reject":
        if version.status != CampaignTermsStatus.PENDING_APPROVAL:
            raise AppError(
                409, "invalid_brief_state",
                f"Cannot reject brief in status {version.status}",
            )
        version.status = CampaignTermsStatus.REJECTED
        # note: free-text rejection notes belong to reward_submissions (0009);
        # brief versions only track the decision status itself.
    else:
        raise AppError(422, "invalid_brief_action", f"Unknown action {action!r}")
    db.flush()
    return version


def list_brief_versions(db: Session, campaign_id: UUID) -> list[CampaignBriefVersion]:
    get_campaign_or_404(db, campaign_id)
    return list(
        db.scalars(
            select(CampaignBriefVersion)
            .where(CampaignBriefVersion.campaign_id == campaign_id)
            .order_by(CampaignBriefVersion.version.asc())
        )
    )


# --- campaign import (JSON / text / file) ----------------------------------------

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


# --- listing ---------------------------------------------------------------------

def list_campaigns(
    db: Session, status: str | None = None, limit: int = 20, offset: int = 0
) -> tuple[list[RewardCampaign], int]:
    q = select(RewardCampaign)
    if status:
        q = q.where(RewardCampaign.status == status)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = list(
        db.scalars(
            q.order_by(RewardCampaign.created_at.desc()).limit(limit).offset(offset)
        )
    )
    return rows, total
