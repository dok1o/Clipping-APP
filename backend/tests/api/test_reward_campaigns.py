"""CR-1 API tests: import (JSON/text/file), terms confirmation, brief decisions,
error format, idempotency, pending_approval without auto-activation."""
import io
import json
from decimal import Decimal

import pytest

TERMS = {
    "payout_model": "cpm",
    "cpm_rate": "10.0000",
    "creator_fee_percent": "10.00",
    "fee_free_budget_threshold": "5000.00",
    "earnings_window_days": 7,
    "payout_hold_days": 3,
    "submission_deadline_minutes": 30,
    "terms_source_url": "https://whop.example/terms",
}


def _json_import(external_campaign_id="api-1", **extra) -> dict:
    payload = {
        "provider": "whop_content_rewards",
        "external_campaign_id": external_campaign_id,
        "name": "API campaign",
        "source_url": f"https://whop.example/{external_campaign_id}",
        "platforms": ["tiktok"],
        "terms": TERMS,
    }
    payload.update(extra)
    return payload


@pytest.fixture
def imported(client):
    def _do(payload: dict):
        r = client.post("/api/v1/reward-campaigns/import", json=payload)
        assert r.status_code == 201, r.text
        return r.json()

    return _do


class TestImportJson:
    def test_import_creates_unconfirmed_everything(self, client, imported):
        body = imported(_json_import(brief={"raw_text": "Post 15-60s with #tag"}))
        assert body["created"] is True
        assert body["terms_created"] is True
        assert body["brief_created"] is True
        assert body["campaign"]["current_terms_version_id"] is None
        assert body["campaign"]["active_brief_version_id"] is None
        assert body["terms_version"]["confirmed_at"] is None
        assert body["brief_version"]["status"] == "pending_approval"

    def test_money_serialized_as_exact_strings(self, client, imported):
        body = imported(_json_import())
        terms = body["terms_version"]
        assert terms["cpm_rate"] == "10.0000"
        assert terms["creator_fee_percent"] == "10.00"
        assert terms["fee_free_budget_threshold"] == "5000.00"

    def test_budget_snapshot_stored(self, client, imported):
        body = imported(
            _json_import(budget_total="5000.00", budget_spent="123.45")
        )
        assert body["campaign"]["budget_total"] == "5000.00"
        assert body["campaign"]["budget_spent"] == "123.45"

    def test_reimport_same_payload_no_duplicates(self, client, imported):
        first = imported(_json_import())
        r = client.post("/api/v1/reward-campaigns/import", json=_json_import())
        assert r.status_code == 201
        second = r.json()
        assert second["created"] is False
        assert second["campaign"]["id"] == first["campaign"]["id"]
        assert second["terms_created"] is False
        assert second["terms_version"]["id"] == first["terms_version"]["id"]
        listing = client.get("/api/v1/reward-campaigns").json()
        assert listing["total"] == 1

    def test_payout_model_matrix_422_error_format(self, client):
        bad = _json_import(terms={**TERMS, "cpm_rate": None})
        r = client.post("/api/v1/reward-campaigns/import", json=bad)
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert detail["code"] == "invalid_campaign_terms"
        assert detail["fields"] and "cpm_rate" in detail["fields"]

    def test_payout_bounds_422(self, client):
        bad = _json_import(
            terms={**TERMS, "min_payout": "10.00", "max_payout_per_clip": "5.00"}
        )
        r = client.post("/api/v1/reward-campaigns/import", json=bad)
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "invalid_campaign_terms"

    def test_per_post_with_cpm_rate_422(self, client):
        bad = _json_import(
            terms={**TERMS, "payout_model": "per_post", "per_post_amount": "100.00"}
        )
        r = client.post("/api/v1/reward-campaigns/import", json=bad)
        assert r.status_code == 422
        assert "cpm_rate" in r.json()["detail"]["fields"]

    def test_currency_must_be_iso3(self, client):
        bad = _json_import(currency="DOLLAR")
        r = client.post("/api/v1/reward-campaigns/import", json=bad)
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "validation_error"

    def test_unknown_platform_422(self, client):
        bad = _json_import(platforms=["vimeo"])
        r = client.post("/api/v1/reward-campaigns/import", json=bad)
        assert r.status_code == 422

    def test_validation_error_format(self, client):
        r = client.post("/api/v1/reward-campaigns/import", json={"name": "no id"})
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert detail["code"] == "validation_error"
        assert isinstance(detail["fields"], dict)


class TestImportText:
    def test_text_import_brief_pending(self, client):
        payload = {
            "external_campaign_id": "txt-1",
            "name": "Text campaign",
            "source_url": "https://whop.example/txt-1",
            "raw_text": "Use sound X, tag @brand, keep 15-60s, disclosure required",
        }
        r = client.post("/api/v1/reward-campaigns/import-text", json=payload)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["brief_version"]["status"] == "pending_approval"
        assert body["brief_version"]["raw_text"].startswith("Use sound X")
        assert body["campaign"]["active_brief_version_id"] is None

    def test_text_import_requires_raw_text(self, client):
        payload = {
            "external_campaign_id": "txt-2",
            "name": "Text campaign",
            "source_url": "https://whop.example/txt-2",
        }
        r = client.post("/api/v1/reward-campaigns/import-text", json=payload)
        assert r.status_code == 422


class TestImportFile:
    def test_json_file(self, client):
        content = json.dumps(_json_import("file-json-1")).encode()
        r = client.post(
            "/api/v1/reward-campaigns/import-file",
            files={"file": ("campaign.json", io.BytesIO(content), "application/json")},
            data={},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["created"] is True
        assert body["terms_version"]["cpm_rate"] == "10.0000"

    def test_text_file_with_form_fields(self, client):
        r = client.post(
            "/api/v1/reward-campaigns/import-file",
            files={"file": ("brief.txt", io.BytesIO("Brief: 15-60s, #tag".encode()), "text/plain")},
            data={
                "external_campaign_id": "file-txt-1",
                "name": "File text campaign",
                "source_url": "https://whop.example/file-txt-1",
                "platforms": "tiktok,youtube",
                "currency": "USD",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["brief_version"]["raw_text"] == "Brief: 15-60s, #tag"
        assert body["brief_version"]["status"] == "pending_approval"
        assert body["campaign"]["platforms"] == ["tiktok", "youtube"]
        # file persisted to S3 (moto) and referenced
        assert body["brief_version"]["raw_file_key"].startswith("briefs/")

    def test_text_file_missing_required_fields_422(self, client):
        r = client.post(
            "/api/v1/reward-campaigns/import-file",
            files={"file": ("brief.txt", io.BytesIO(b"text"), "text/plain")},
            data={"provider": "whop_content_rewards"},
        )
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "invalid_import_file"

    def test_bad_extension_415(self, client):
        r = client.post(
            "/api/v1/reward-campaigns/import-file",
            files={"file": ("brief.docx", io.BytesIO(b"x"), "application/octet-stream")},
            data={},
        )
        assert r.status_code == 415
        assert r.json()["detail"]["code"] == "unsupported_media"

    def test_invalid_json_file_422(self, client):
        r = client.post(
            "/api/v1/reward-campaigns/import-file",
            files={"file": ("c.json", io.BytesIO(b"{oops"), "application/json")},
            data={},
        )
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "invalid_import_file"


class TestTermsEndpoints:
    def test_get_terms_history(self, client, imported):
        body = imported(_json_import())
        campaign_id = body["campaign"]["id"]
        r = client.get(f"/api/v1/reward-campaigns/{campaign_id}/terms")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["version"] == 1

    def test_post_new_terms_version(self, client, imported):
        body = imported(_json_import())
        campaign_id = body["campaign"]["id"]
        r = client.post(
            f"/api/v1/reward-campaigns/{campaign_id}/terms",
            json={**TERMS, "creator_fee_percent": "12.00"},
        )
        assert r.status_code == 201, r.text
        assert r.json()["version"] == 2

    def test_post_same_terms_reuses_version(self, client, imported):
        body = imported(_json_import())
        campaign_id = body["campaign"]["id"]
        r = client.post(f"/api/v1/reward-campaigns/{campaign_id}/terms", json=TERMS)
        assert r.status_code == 201
        assert r.json()["version"] == 1  # reused, not duplicated

    def test_patch_confirm_moves_pointer(self, client, imported):
        body = imported(_json_import())
        campaign_id = body["campaign"]["id"]
        version_id = body["terms_version"]["id"]
        r = client.patch(
            f"/api/v1/reward-campaigns/{campaign_id}/terms",
            json={"version_id": version_id, "confirm": True},
        )
        assert r.status_code == 200, r.text
        assert r.json()["current_terms_version_id"] == version_id

    def test_patch_confirm_unknown_version_404(self, client, imported):
        body = imported(_json_import())
        r = client.patch(
            f"/api/v1/reward-campaigns/{body['campaign']['id']}/terms",
            json={"version_id": "00000000-0000-0000-0000-000000000000"},
        )
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "terms_version_not_found"

    def test_confirm_false_422(self, client, imported):
        body = imported(_json_import())
        r = client.patch(
            f"/api/v1/reward-campaigns/{body['campaign']['id']}/terms",
            json={"version_id": body["terms_version"]["id"], "confirm": False},
        )
        assert r.status_code == 422


class TestBriefEndpoints:
    def test_post_brief_pending_with_assets_unauthorized(self, client, imported):
        body = imported(_json_import())
        campaign_id = body["campaign"]["id"]
        r = client.post(
            f"/api/v1/reward-campaigns/{campaign_id}/brief",
            json={
                "raw_text": "second brief",
                "source_assets": [
                    {"kind": "link", "title": "Brand assets", "external_url": "https://b.example"}
                ],
            },
        )
        assert r.status_code == 201, r.text
        brief = r.json()
        assert brief["status"] == "pending_approval"
        assert brief["assets"][0]["authorized"] is False
        # active pointer untouched
        detail = client.get(f"/api/v1/reward-campaigns/{campaign_id}").json()
        assert detail["active_brief_version_id"] is None

    def test_patch_approve_activates(self, client, imported):
        body = imported(_json_import(brief={"raw_text": "v1"}))
        campaign_id = body["campaign"]["id"]
        brief_id = body["brief_version"]["id"]
        r = client.patch(
            f"/api/v1/reward-campaigns/{campaign_id}/brief",
            json={"version_id": brief_id, "action": "approve"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved"
        detail = client.get(f"/api/v1/reward-campaigns/{campaign_id}").json()
        assert detail["active_brief_version_id"] == brief_id

    def test_patch_reject_no_activation(self, client, imported):
        body = imported(_json_import(brief={"raw_text": "v1"}))
        campaign_id = body["campaign"]["id"]
        r = client.patch(
            f"/api/v1/reward-campaigns/{campaign_id}/brief",
            json={"version_id": body["brief_version"]["id"], "action": "reject"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"
        detail = client.get(f"/api/v1/reward-campaigns/{campaign_id}").json()
        assert detail["active_brief_version_id"] is None

    def test_approve_rejected_conflict_409(self, client, imported):
        body = imported(_json_import(brief={"raw_text": "v1"}))
        campaign_id = body["campaign"]["id"]
        client.patch(
            f"/api/v1/reward-campaigns/{campaign_id}/brief",
            json={"version_id": body["brief_version"]["id"], "action": "reject"},
        )
        r = client.patch(
            f"/api/v1/reward-campaigns/{campaign_id}/brief",
            json={"version_id": body["brief_version"]["id"], "action": "approve"},
        )
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "invalid_brief_state"

    def test_brief_list(self, client, imported):
        body = imported(_json_import(brief={"raw_text": "v1"}))
        campaign_id = body["campaign"]["id"]
        r = client.get(f"/api/v1/reward-campaigns/{campaign_id}/brief")
        assert r.status_code == 200
        assert r.json()["total"] == 1


class TestCampaignEndpoints:
    def test_get_unknown_campaign_404(self, client):
        r = client.get("/api/v1/reward-campaigns/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "campaign_not_found"

    def test_list_with_status_filter(self, client, imported):
        imported(_json_import("list-1", status="active"))
        imported(_json_import("list-2", status="draft"))
        r = client.get("/api/v1/reward-campaigns", params={"status": "active"})
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["status"] == "active"
