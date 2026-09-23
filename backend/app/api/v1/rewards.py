"""Content Rewards campaign API (CONTRACTS CR-4.3 subset — CR-1).

Thin HTTP layer: validation/statuses/service calls only. Import never confirms
terms and never activates briefs; confirmation/approval are explicit PATCHes.
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_storage
from app.schemas.rewards import (
    BriefCreate,
    BriefDecision,
    BriefVersionRead,
    CampaignImportRequest,
    CampaignPage,
    ImportResultRead,
    RewardCampaignRead,
    TermsConfirm,
    TermsCreate,
    TermsVersionRead,
    TextImportRequest,
)
from app.services.rewards import campaign_service

router = APIRouter(tags=["reward-campaigns"])


def _import_result(outcome) -> ImportResultRead:
    return ImportResultRead(
        campaign=RewardCampaignRead.model_validate(outcome.campaign),
        created=outcome.created,
        terms_version=(
            TermsVersionRead.model_validate(outcome.terms_version)
            if outcome.terms_version is not None
            else None
        ),
        terms_created=outcome.terms_created,
        brief_version=(
            BriefVersionRead.model_validate(outcome.brief_version)
            if outcome.brief_version is not None
            else None
        ),
        brief_created=outcome.brief_created,
    )


@router.post("/reward-campaigns/import", status_code=201, response_model=ImportResultRead)
def import_campaign_json(payload: CampaignImportRequest, db: Session = Depends(get_db)):
    """JSON import: campaign + optional terms + optional brief."""
    return _import_result(campaign_service.import_campaign(db, payload))


@router.post("/reward-campaigns/import-text", status_code=201, response_model=ImportResultRead)
def import_campaign_text(payload: TextImportRequest, db: Session = Depends(get_db)):
    """Text import: campaign fields + brief as plain raw_text."""
    return _import_result(campaign_service.import_text(db, payload))


@router.post("/reward-campaigns/import-file", status_code=201, response_model=ImportResultRead)
async def import_campaign_file(
    file: UploadFile = File(...),
    provider: str = Form("whop_content_rewards"),
    external_campaign_id: str = Form(""),
    name: str = Form(""),
    source_url: str = Form(""),
    brand_name: str | None = Form(None),
    status: str = Form("draft"),
    platforms: str = Form(""),
    currency: str = Form("USD"),
    budget_total: str | None = Form(None),
    budget_spent: str | None = Form(None),
    deadline_at: str | None = Form(None),
    db: Session = Depends(get_db),
    storage=Depends(get_storage),
):
    """File import: .json = full import request; .txt/.md = brief text file.

    Form fields carry campaign identity for text files (ignored for .json,
    which contains the whole structure).
    """
    content = await file.read()
    platforms_list = [p.strip() for p in platforms.split(",") if p.strip()]
    deadline = None
    if deadline_at:
        try:
            deadline = datetime.fromisoformat(deadline_at.replace("Z", "+00:00"))
        except ValueError:
            deadline = "invalid"  # -> service 422 invalid_import_file
    form_fields = {
        "provider": provider,
        "external_campaign_id": external_campaign_id,
        "name": name,
        "source_url": source_url,
        "brand_name": brand_name,
        "status": status,
        "platforms": platforms_list,
        "currency": currency,
        "budget_total": budget_total,
        "budget_spent": budget_spent,
        "deadline_at": deadline,
    }
    outcome = campaign_service.import_file(
        db,
        filename=file.filename or "",
        content=content,
        form_fields=form_fields,
        storage=storage,
    )
    return _import_result(outcome)


@router.get("/reward-campaigns", response_model=CampaignPage)
def list_campaigns(
    status: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> CampaignPage:
    rows, total = campaign_service.list_campaigns(db, status, limit, offset)
    return CampaignPage(
        items=[RewardCampaignRead.model_validate(r) for r in rows], total=total
    )


@router.get("/reward-campaigns/{campaign_id}", response_model=RewardCampaignRead)
def get_campaign(campaign_id: uuid.UUID, db: Session = Depends(get_db)):
    return campaign_service.get_campaign_or_404(db, campaign_id)


# --- terms (immutable versioned; confirmation is explicit) ----------------------

@router.get("/reward-campaigns/{campaign_id}/terms")
def list_terms(campaign_id: uuid.UUID, db: Session = Depends(get_db)):
    rows = campaign_service.list_terms_versions(db, campaign_id)
    return {
        "items": [TermsVersionRead.model_validate(r) for r in rows],
        "total": len(rows),
    }


@router.post("/reward-campaigns/{campaign_id}/terms", status_code=201, response_model=TermsVersionRead)
def create_terms(campaign_id: uuid.UUID, payload: TermsCreate, db: Session = Depends(get_db)):
    version, _created = campaign_service.add_terms_version(db, campaign_id, payload)
    db.commit()
    return version


@router.patch("/reward-campaigns/{campaign_id}/terms", response_model=RewardCampaignRead)
def confirm_terms(campaign_id: uuid.UUID, payload: TermsConfirm, db: Session = Depends(get_db)):
    """Explicit user confirmation of a terms version (moves the pointer)."""
    if not payload.confirm:
        from app.core.errors import AppError

        raise AppError(422, "invalid_terms_confirmation", "confirm must be true")
    campaign, _version = campaign_service.confirm_terms(db, campaign_id, payload.version_id)
    db.commit()
    return campaign


# --- brief (pending_approval; approve/reject are explicit) ----------------------

@router.get("/reward-campaigns/{campaign_id}/brief")
def list_briefs(campaign_id: uuid.UUID, db: Session = Depends(get_db)):
    rows = campaign_service.list_brief_versions(db, campaign_id)
    return {
        "items": [BriefVersionRead.model_validate(r) for r in rows],
        "total": len(rows),
    }


@router.post(
    "/reward-campaigns/{campaign_id}/brief", status_code=201, response_model=BriefVersionRead
)
def create_brief(campaign_id: uuid.UUID, payload: BriefCreate, db: Session = Depends(get_db)):
    version, _created = campaign_service.add_brief_version(
        db,
        campaign_id,
        raw_text=payload.raw_text,
        structured_json=payload.structured_json,
        source_url=payload.source_url or "",
        source_assets=payload.source_assets,
    )
    db.commit()
    return version


@router.patch(
    "/reward-campaigns/{campaign_id}/brief", status_code=200, response_model=BriefVersionRead
)
def decide_brief(campaign_id: uuid.UUID, payload: BriefDecision, db: Session = Depends(get_db)):
    version = campaign_service.decide_brief(db, campaign_id, payload.version_id, payload.action)
    db.commit()
    return version
