"""CR-1 model integrity: CHECKs, FK policies, uniques, exact Numeric types,
and the v2.1 invariant — NO economic term fields in reward_campaigns."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.db import session as db_session
from app.models.rewards import (
    CampaignBriefVersion,
    CampaignSourceAsset,
    CampaignTermsVersion,
    RewardCampaign,
)


@pytest.fixture
def db(tmp_path: Path):
    from app.db.base import Base

    db_session.init_engine(f"sqlite+pysqlite:///{tmp_path / 'cr_models.db'}")
    Base.metadata.create_all(db_session.get_engine())  # tests only (§9)
    session = db_session.session_factory()
    yield session
    session.close()
    db_session.reset_engine()


def _campaign(db, **kw) -> RewardCampaign:
    c = RewardCampaign(
        provider=kw.pop("provider", "whop_content_rewards"),
        external_campaign_id=kw.pop("external_campaign_id", "ext-1"),
        name=kw.pop("name", "Test campaign"),
        source_url=kw.pop("source_url", "https://whop.example/campaign"),
        status=kw.pop("status", "draft"),
        currency=kw.pop("currency", "USD"),
        **kw,
    )
    db.add(c)
    db.commit()
    return c


def _terms(db, campaign_id, version=1, **kw) -> CampaignTermsVersion:
    fields = dict(
        campaign_id=campaign_id,
        version=version,
        content_hash=kw.pop("content_hash", "a" * 64),
        payout_model="cpm",
        cpm_rate=Decimal("10.0000"),
        creator_fee_percent=Decimal("10.00"),
        fee_free_budget_threshold=Decimal("5000.00"),
        earnings_window_days=7,
        payout_hold_days=3,
        submission_deadline_minutes=30,
        terms_source_url="https://whop.example/terms",
        terms_checked_at=datetime(2026, 9, 23, tzinfo=timezone.utc),
    )
    fields.update(kw)
    t = CampaignTermsVersion(**fields)
    db.add(t)
    db.commit()
    return t


class TestRewardCampaign:
    def test_no_economic_term_columns(self) -> None:
        """v2.1: economic terms live ONLY in campaign_terms_versions."""
        cols = {c.name for c in RewardCampaign.__table__.columns}
        forbidden = {
            "payout_model", "cpm_rate", "per_post_amount", "retainer_amount",
            "retainer_cycle_days", "min_payout", "max_payout_per_clip",
        }
        assert not (cols & forbidden), f"term fields leaked into reward_campaigns: {cols & forbidden}"
        assert {"provider", "external_campaign_id", "currency", "budget_total", "budget_spent",
                "current_terms_version_id", "active_brief_version_id"} <= cols

    def test_exact_numeric_types(self) -> None:
        cols = {c.name: c.type for c in RewardCampaign.__table__.columns}
        assert str(cols["budget_total"]) == "NUMERIC(14, 2)"
        assert str(cols["budget_spent"]) == "NUMERIC(14, 2)"
        tcols = {c.name: c.type for c in CampaignTermsVersion.__table__.columns}
        assert str(tcols["cpm_rate"]) == "NUMERIC(10, 4)"
        assert str(tcols["per_post_amount"]) == "NUMERIC(14, 2)"
        assert str(tcols["retainer_amount"]) == "NUMERIC(14, 2)"
        assert str(tcols["min_payout"]) == "NUMERIC(14, 2)"
        assert str(tcols["max_payout_per_clip"]) == "NUMERIC(14, 2)"
        assert str(tcols["creator_fee_percent"]) == "NUMERIC(5, 2)"
        assert str(tcols["fee_free_budget_threshold"]) == "NUMERIC(14, 2)"

    def test_unique_provider_external_id(self, db) -> None:
        _campaign(db, external_campaign_id="dup")
        with pytest.raises(IntegrityError):
            _campaign(db, external_campaign_id="dup")
        db.rollback()

    def test_status_check(self, db) -> None:
        with pytest.raises(IntegrityError):
            _campaign(db, status="weird")
        db.rollback()

    def test_currency_len_check(self, db) -> None:
        with pytest.raises(IntegrityError):
            _campaign(db, currency="US")
        db.rollback()

    def test_circular_pointers_set_null_on_version_delete(self, db) -> None:
        """Deleting a terms version NULLs the campaign pointer (no cascade back)."""
        c = _campaign(db)
        t = _terms(db, c.id)
        db.refresh(c)
        c.current_terms_version_id = t.id
        db.commit()
        db.delete(t)
        db.commit()
        db.refresh(c)
        assert c.current_terms_version_id is None


class TestCampaignTermsVersion:
    def test_unique_campaign_version(self, db) -> None:
        c = _campaign(db)
        _terms(db, c.id, version=1)
        with pytest.raises(IntegrityError):
            _terms(db, c.id, version=1)
        db.rollback()

    def test_version_must_be_positive(self, db) -> None:
        c = _campaign(db)
        with pytest.raises(IntegrityError):
            _terms(db, c.id, version=0)
        db.rollback()

    def test_unknown_payout_model_rejected(self, db) -> None:
        c = _campaign(db)
        with pytest.raises(IntegrityError):
            _terms(db, c.id, payout_model="revshare")
        db.rollback()

    @pytest.mark.parametrize(
        "fields",
        [
            # cpm without rate
            {"payout_model": "cpm", "cpm_rate": None},
            # cpm with per_post amount set
            {"payout_model": "cpm", "cpm_rate": Decimal("1"), "per_post_amount": Decimal("5")},
            # per_post without amount
            {"payout_model": "per_post", "per_post_amount": None, "cpm_rate": None},
            # per_post with cpm rate set
            {"payout_model": "per_post", "per_post_amount": Decimal("5"), "cpm_rate": Decimal("1")},
            # retainer without amount
            {"payout_model": "retainer", "retainer_amount": None, "retainer_cycle_days": 30},
            # retainer without cycle days
            {"payout_model": "retainer", "retainer_amount": Decimal("100"), "retainer_cycle_days": None},
            # retainer with cpm rate set
            {"payout_model": "retainer", "retainer_amount": Decimal("100"),
             "retainer_cycle_days": 30, "cpm_rate": Decimal("1")},
            # retainer with per_post amount set
            {"payout_model": "retainer", "retainer_amount": Decimal("100"),
             "retainer_cycle_days": 30, "per_post_amount": Decimal("5")},
        ],
    )
    def test_payout_model_matrix_db_check(self, db, fields) -> None:
        c = _campaign(db)
        with pytest.raises(IntegrityError):
            _terms(db, c.id, **fields)
        db.rollback()

    def test_max_payout_below_min_rejected(self, db) -> None:
        c = _campaign(db)
        with pytest.raises(IntegrityError):
            _terms(
                db, c.id,
                min_payout=Decimal("10.00"), max_payout_per_clip=Decimal("5.00"),
            )
        db.rollback()

    def test_negative_fee_percent_rejected(self, db) -> None:
        c = _campaign(db)
        with pytest.raises(IntegrityError):
            _terms(db, c.id, creator_fee_percent=Decimal("-1.00"))
        db.rollback()

    def test_fee_percent_over_100_rejected(self, db) -> None:
        c = _campaign(db)
        with pytest.raises(IntegrityError):
            _terms(db, c.id, creator_fee_percent=Decimal("100.01"))
        db.rollback()

    def test_nonpositive_amounts_rejected(self, db) -> None:
        c = _campaign(db)
        with pytest.raises(IntegrityError):
            _terms(db, c.id, cpm_rate=Decimal("0"))
        db.rollback()
        with pytest.raises(IntegrityError):
            _terms(db, c.id, fee_free_budget_threshold=Decimal("-1"))
        db.rollback()

    def test_nonpositive_windows_rejected(self, db) -> None:
        c = _campaign(db)
        with pytest.raises(IntegrityError):
            _terms(db, c.id, submission_deadline_minutes=0)
        db.rollback()
        with pytest.raises(IntegrityError):
            _terms(db, c.id, earnings_window_days=0)
        db.rollback()

    def test_campaign_delete_cascades_versions(self, db) -> None:
        c = _campaign(db)
        _terms(db, c.id, version=1)
        _terms(db, c.id, version=2, content_hash="b" * 64)
        db.delete(c)
        db.commit()
        assert db.query(CampaignTermsVersion).count() == 0


class TestCampaignBriefVersion:
    def test_unique_campaign_version(self, db) -> None:
        c = _campaign(db)
        db.add(CampaignBriefVersion(
            campaign_id=c.id, version=1, status="pending_approval",
            raw_text="brief", source_url="https://x",
        ))
        db.commit()
        db.add(CampaignBriefVersion(
            campaign_id=c.id, version=1, status="pending_approval",
            raw_text="brief v2", source_url="https://x",
        ))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_status_check(self, db) -> None:
        c = _campaign(db)
        db.add(CampaignBriefVersion(
            campaign_id=c.id, version=1, status="active",
            raw_text="brief", source_url="https://x",
        ))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_source_present_check(self, db) -> None:
        c = _campaign(db)
        db.add(CampaignBriefVersion(
            campaign_id=c.id, version=1, status="pending_approval",
            source_url="https://x",
        ))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


class TestCampaignSourceAsset:
    def test_default_authorized_false(self, db) -> None:
        c = _campaign(db)
        b = CampaignBriefVersion(
            campaign_id=c.id, version=1, status="pending_approval",
            raw_text="brief", source_url="https://x",
        )
        db.add(b)
        db.commit()
        a = CampaignSourceAsset(
            campaign_id=c.id, brief_version_id=b.id, kind="link",
            external_url="https://brand.example/logo", title="Brand kit",
        )
        db.add(a)
        db.commit()
        assert a.authorized is False

    def test_kind_check(self, db) -> None:
        c = _campaign(db)
        b = CampaignBriefVersion(
            campaign_id=c.id, version=1, status="pending_approval",
            raw_text="brief", source_url="https://x",
        )
        db.add(b)
        db.commit()
        db.add(CampaignSourceAsset(
            campaign_id=c.id, brief_version_id=b.id, kind="doc",
            external_url="https://x", title="t",
        ))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_location_present_check(self, db) -> None:
        c = _campaign(db)
        b = CampaignBriefVersion(
            campaign_id=c.id, version=1, status="pending_approval",
            raw_text="brief", source_url="https://x",
        )
        db.add(b)
        db.commit()
        db.add(CampaignSourceAsset(
            campaign_id=c.id, brief_version_id=b.id, kind="link", title="t",
        ))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_fk_policies_in_metadata(self) -> None:
        """FK ondelete policies per contract: CASCADE to campaign/brief,
        SET NULL for the circular campaign pointers."""
        def _fk_set(table):
            return {
                (fk.parent.name, fk.column.table.name, fk.ondelete)
                for fk in table.__table__.foreign_keys
            }

        fks_terms = _fk_set(CampaignTermsVersion)
        assert ("campaign_id", "reward_campaigns", "CASCADE") in fks_terms
        fks_campaign = _fk_set(RewardCampaign)
        assert ("current_terms_version_id", "campaign_terms_versions", "SET NULL") in fks_campaign
        assert ("active_brief_version_id", "campaign_brief_versions", "SET NULL") in fks_campaign
        fks_asset = _fk_set(CampaignSourceAsset)
        assert ("campaign_id", "reward_campaigns", "CASCADE") in fks_asset
        assert ("brief_version_id", "campaign_brief_versions", "CASCADE") in fks_asset
