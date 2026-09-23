"""Campaign service tests: deterministic import, immutable versioned terms,
explicit confirmation, pending_approval briefs, authorized=false assets."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.db import session as db_session
from app.models.rewards import (
    CampaignBriefVersion,
    CampaignSourceAsset,
    CampaignTermsVersion,
    RewardCampaign,
)
from app.schemas.rewards import (
    BriefInput,
    CampaignImportRequest,
    SourceAssetInput,
    TermsInput,
    TextImportRequest,
)
from app.services.rewards import campaign_service as svc

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path: Path):
    from app.db.base import Base

    db_session.init_engine(f"sqlite+pysqlite:///{tmp_path / 'cr_svc.db'}")
    Base.metadata.create_all(db_session.get_engine())  # tests only
    session = db_session.session_factory()
    yield session
    session.close()
    db_session.reset_engine()


def _terms_req(**kw) -> TermsInput:
    base = dict(
        payout_model="cpm",
        cpm_rate=Decimal("10.0000"),
        creator_fee_percent=Decimal("10.00"),
        fee_free_budget_threshold=Decimal("5000.00"),
        earnings_window_days=7,
        payout_hold_days=3,
        submission_deadline_minutes=30,
        terms_source_url="https://whop.example/terms",
        terms_checked_at=NOW,
    )
    base.update(kw)
    return TermsInput(**base)


def _import_req(**kw) -> CampaignImportRequest:
    base = dict(
        provider="whop_content_rewards",
        external_campaign_id="camp-1",
        name="Music boost",
        source_url="https://whop.example/camp-1",
        platforms=["tiktok", "youtube"],
    )
    base.update(kw)
    return CampaignImportRequest(**base)


class TestImportDeterminism:
    def test_first_import_creates_campaign_terms_brief(self, db) -> None:
        out = svc.import_campaign(db, _import_req(
            terms=_terms_req(),
            brief=BriefInput(
                raw_text="Use the sound, tag @brand, 15-60s",
                source_assets=[
                    SourceAssetInput(kind="link", title="Brand kit", external_url="https://b.example/kit")
                ],
            ),
        ))
        assert out.created is True
        assert out.terms_created is True
        assert out.brief_created is True
        assert out.terms_version.version == 1
        assert out.brief_version.version == 1
        assert out.terms_version.confirmed_at is None
        assert out.campaign.current_terms_version_id is None
        assert out.campaign.active_brief_version_id is None
        assert out.brief_version.status == "pending_approval"
        asset = db.query(CampaignSourceAsset).one()
        assert asset.authorized is False
        assert asset.brief_version_id == out.brief_version.id

    def test_reimport_same_payload_is_idempotent(self, db) -> None:
        req = _import_req(terms=_terms_req(), imported_payload={"k": "v"})
        first = svc.import_campaign(db, req)
        second = svc.import_campaign(db, req)
        assert second.created is False
        assert second.campaign.id == first.campaign.id
        assert second.terms_created is False
        assert second.terms_version.id == first.terms_version.id
        assert second.brief_created is False  # no brief in request
        assert db.query(RewardCampaign).count() == 1
        assert db.query(CampaignTermsVersion).count() == 1

    def test_reimport_with_same_brief_reuses_version(self, db) -> None:
        req = _import_req(brief=BriefInput(raw_text="Brief text", source_url="https://whop.example/camp-1"))
        first = svc.import_campaign(db, req)
        second = svc.import_campaign(db, req)
        assert second.brief_created is False
        assert second.brief_version.id == first.brief_version.id
        assert db.query(CampaignBriefVersion).count() == 1

    def test_reimport_updates_operational_snapshot(self, db) -> None:
        svc.import_campaign(db, _import_req(status="draft", budget_total=None))
        out = svc.import_campaign(db, _import_req(
            status="active", budget_total=Decimal("5000.00"), budget_spent=Decimal("100.00"),
        ))
        assert out.created is False
        assert out.campaign.status == "active"
        assert out.campaign.budget_total == Decimal("5000.00")

    def test_changed_terms_create_next_version(self, db) -> None:
        first = svc.import_campaign(db, _import_req(terms=_terms_req()))
        second = svc.import_campaign(db, _import_req(
            terms=_terms_req(creator_fee_percent=Decimal("12.00")),
        ))
        assert second.terms_created is True
        assert second.terms_version.version == 2
        assert db.query(CampaignTermsVersion).count() == 2
        # v1 untouched (immutable): same hash, still unconfirmed
        db.refresh(first.terms_version)
        assert first.terms_version.version == 1
        assert first.terms_version.creator_fee_percent == Decimal("10.00")


class TestTermsValidation:
    @pytest.mark.parametrize(
        "fields",
        [
            {"payout_model": "cpm", "cpm_rate": None},
            {"payout_model": "cpm", "per_post_amount": Decimal("5.00")},
            {"payout_model": "per_post", "cpm_rate": Decimal("1.0")},
            {"payout_model": "retainer", "retainer_cycle_days": None},
            {"payout_model": "retainer", "per_post_amount": Decimal("5.00")},
        ],
    )
    def test_matrix_violations_rejected_422(self, db, fields) -> None:
        with pytest.raises(AppError) as err:
            svc.import_campaign(db, _import_req(terms=_terms_req(**fields)))
        assert err.value.status_code == 422
        assert err.value.code == "invalid_campaign_terms"
        assert isinstance(err.value.fields, dict) and err.value.fields

    def test_max_below_min_rejected(self, db) -> None:
        with pytest.raises(AppError) as err:
            svc.import_campaign(db, _import_req(terms=_terms_req(
                min_payout=Decimal("10.00"), max_payout_per_clip=Decimal("5.00"),
            )))
        assert err.value.code == "invalid_campaign_terms"
        assert "max_payout_per_clip" in err.value.fields

    def test_valid_per_post_and_retainer(self, db) -> None:
        out = svc.import_campaign(db, _import_req(terms=_terms_req(
            payout_model="per_post", cpm_rate=None, per_post_amount=Decimal("250.00"),
        )))
        assert out.terms_version.payout_model == "per_post"
        out2 = svc.import_campaign(db, _import_req(
            external_campaign_id="camp-2",
            terms=_terms_req(
                payout_model="retainer", cpm_rate=None,
                retainer_amount=Decimal("1000.00"), retainer_cycle_days=30,
            ),
        ))
        assert out2.terms_version.retainer_cycle_days == 30


class TestTermsLifecycle:
    def test_confirm_moves_pointer_and_stamps_time(self, db) -> None:
        out = svc.import_campaign(db, _import_req(terms=_terms_req()))
        campaign, version = svc.confirm_terms(db, out.campaign.id, out.terms_version.id)
        assert campaign.current_terms_version_id == version.id
        assert version.confirmed_at is not None

    def test_confirm_is_idempotent(self, db) -> None:
        out = svc.import_campaign(db, _import_req(terms=_terms_req()))
        _, v1 = svc.confirm_terms(db, out.campaign.id, out.terms_version.id)
        first_confirmed = v1.confirmed_at
        _, v2 = svc.confirm_terms(db, out.campaign.id, out.terms_version.id)
        assert v2.confirmed_at == first_confirmed
        assert db.query(CampaignTermsVersion).count() == 1

    def test_confirm_new_version_moves_pointer_only_on_action(self, db) -> None:
        out = svc.import_campaign(db, _import_req(terms=_terms_req()))
        v2, _ = svc.add_terms_version(
            db, out.campaign.id, _terms_req(creator_fee_percent=Decimal("0"))
        )
        db.commit()
        db.refresh(out.campaign)
        # pointer still on v1? No — it was never set; import never confirms
        assert out.campaign.current_terms_version_id is None
        svc.confirm_terms(db, out.campaign.id, v2.id)
        db.commit()
        db.refresh(out.campaign)
        assert out.campaign.current_terms_version_id == v2.id

    def test_confirm_wrong_campaign_404(self, db) -> None:
        out = svc.import_campaign(db, _import_req(terms=_terms_req()))
        other_id = uuid.uuid4()
        with pytest.raises(AppError) as err:
            svc.confirm_terms(db, other_id, out.terms_version.id)
        assert err.value.status_code == 404

    def test_import_never_confirms(self, db) -> None:
        """Even a re-import of already-confirmed terms does not touch the pointer."""
        out = svc.import_campaign(db, _import_req(terms=_terms_req()))
        svc.confirm_terms(db, out.campaign.id, out.terms_version.id)
        db.commit()
        again = svc.import_campaign(db, _import_req(terms=_terms_req()))
        db.refresh(again.campaign)
        assert again.campaign.current_terms_version_id == out.terms_version.id
        assert again.terms_version.confirmed_at is not None  # reuse, not a new row


class TestBriefLifecycle:
    def test_add_brief_requires_source(self, db) -> None:
        out = svc.import_campaign(db, _import_req())
        with pytest.raises(AppError) as err:
            svc.add_brief_version(db, out.campaign.id, source_url=out.campaign.source_url)
        assert err.value.status_code == 422

    def test_approve_sets_active_pointer_and_supersedes(self, db) -> None:
        out = svc.import_campaign(db, _import_req(brief=BriefInput(raw_text="v1")))
        v1 = out.brief_version
        approved = svc.decide_brief(db, out.campaign.id, v1.id, "approve")
        db.commit()
        assert approved.status == "approved"
        assert approved.approved_at is not None
        db.refresh(out.campaign)
        assert out.campaign.active_brief_version_id == v1.id

        v2, _ = svc.add_brief_version(
            db, out.campaign.id, raw_text="v2", source_url=out.campaign.source_url
        )
        db.commit()
        assert v2.status == "pending_approval"
        db.refresh(out.campaign)
        assert out.campaign.active_brief_version_id == v1.id  # no auto-activation
        svc.decide_brief(db, out.campaign.id, v2.id, "approve")
        db.commit()
        db.refresh(v1)
        assert v1.status == "superseded"
        db.refresh(out.campaign)
        assert out.campaign.active_brief_version_id == v2.id

    def test_reject_keeps_pointer_null(self, db) -> None:
        out = svc.import_campaign(db, _import_req(brief=BriefInput(raw_text="v1")))
        rejected = svc.decide_brief(db, out.campaign.id, out.brief_version.id, "reject")
        db.commit()
        assert rejected.status == "rejected"
        db.refresh(out.campaign)
        assert out.campaign.active_brief_version_id is None

    def test_reapprove_is_idempotent(self, db) -> None:
        out = svc.import_campaign(db, _import_req(brief=BriefInput(raw_text="v1")))
        svc.decide_brief(db, out.campaign.id, out.brief_version.id, "approve")
        again = svc.decide_brief(db, out.campaign.id, out.brief_version.id, "approve")
        assert again.status == "approved"

    def test_approve_rejected_conflict(self, db) -> None:
        out = svc.import_campaign(db, _import_req(brief=BriefInput(raw_text="v1")))
        svc.decide_brief(db, out.campaign.id, out.brief_version.id, "reject")
        with pytest.raises(AppError) as err:
            svc.decide_brief(db, out.campaign.id, out.brief_version.id, "approve")
        assert err.value.status_code == 409

    def test_text_import_uses_raw_text(self, db) -> None:
        req = TextImportRequest(
            external_campaign_id="camp-txt",
            name="Text campaign",
            source_url="https://whop.example/txt",
            raw_text="Post with #tag, disclosure in caption",
        )
        out = svc.import_text(db, req)
        assert out.brief_version.raw_text == "Post with #tag, disclosure in caption"
        assert out.brief_version.status == "pending_approval"


class TestImportFile:
    def test_json_file_import(self, db) -> None:
        import json

        payload = {
            "provider": "whop_content_rewards",
            "external_campaign_id": "camp-file",
            "name": "File campaign",
            "source_url": "https://whop.example/file",
            "terms": {
                "payout_model": "per_post",
                "per_post_amount": "150.00",
                "creator_fee_percent": "0",
                "fee_free_budget_threshold": "5000.00",
                "earnings_window_days": 7,
                "payout_hold_days": 3,
                "submission_deadline_minutes": 30,
                "terms_source_url": "https://whop.example/terms",
            },
            "brief": {"raw_text": "FromFile brief"},
        }
        out = svc.import_file(
            db,
            filename="campaign.json",
            content=json.dumps(payload).encode(),
            form_fields={},
            storage=None,
        )
        assert out.created is True
        assert out.terms_version.per_post_amount == Decimal("150.00")
        assert out.brief_version.raw_text == "FromFile brief"

    def test_json_file_reimport_idempotent(self, db) -> None:
        import json

        content = json.dumps({
            "external_campaign_id": "camp-file-2",
            "name": "File campaign",
            "source_url": "https://whop.example/file2",
            "brief": {"raw_text": "Same brief"},
        }).encode()
        first = svc.import_file(db, filename="c.json", content=content, form_fields={}, storage=None)
        second = svc.import_file(db, filename="c.json", content=content, form_fields={}, storage=None)
        assert second.created is False
        assert second.brief_created is False
        assert second.brief_version.id == first.brief_version.id

    def test_text_file_requires_campaign_fields(self, db) -> None:
        with pytest.raises(AppError) as err:
            svc.import_file(
                db, filename="brief.txt",
                content=b"some brief text",
                form_fields={"provider": "whop_content_rewards"},  # missing required
                storage=None,
            )
        assert err.value.status_code == 422
        assert err.value.code == "invalid_import_file"

    def test_bad_extension_rejected(self, db) -> None:
        with pytest.raises(AppError) as err:
            svc.import_file(db, filename="brief.docx", content=b"x", form_fields={}, storage=None)
        assert err.value.status_code == 415

    def test_invalid_json_rejected(self, db) -> None:
        with pytest.raises(AppError) as err:
            svc.import_file(db, filename="c.json", content=b"{not json", form_fields={}, storage=None)
        assert err.value.code == "invalid_import_file"

    def test_json_array_rejected(self, db) -> None:
        import json

        with pytest.raises(AppError) as err:
            svc.import_file(
                db, filename="c.json", content=json.dumps([1, 2]).encode(),
                form_fields={}, storage=None,
            )
        assert err.value.code == "invalid_import_file"
