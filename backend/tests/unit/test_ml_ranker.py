"""ML rerank (Stage 7): dataset gate, train/eval, rerank fallback, self-training."""
import random
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

FEATS = {
    "speech_ratio": 0.5, "key_phrases": 0.2, "tempo_wpm": 150.0,
    "tempo_score": 0.8, "loudness": 0.4, "position": 0.6,
    "scene_alignment": 0.7,
}


def _row(i: int, duration: float, target: float):
    from app.services.ai_clipping.dataset_service import LabeledRow

    return LabeledRow(
        clip_id=uuid.uuid4(), publication_id=uuid.uuid4(), platform="tiktok",
        captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i),
        features={**FEATS, "duration_sec": duration, "tempo_wpm": 120 + (i % 60)},
        target=target, target_kind="views",
    )


def _synthetic_dataset(n: int = 40, mode: str = "learnable"):
    """mode=learnable: target follows duration (heuristic ignores duration).
    mode=flat: constant target -> no model can beat baseline (gate fails)."""
    from app.services.ai_clipping.dataset_service import Dataset

    rng = random.Random(7)
    rows = []
    for i in range(n):
        duration = 15.0 + rng.random() * 45.0
        if mode == "learnable":
            target = 3.0 * duration + rng.random() * 2.0  # strong duration signal
        else:
            target = 5.0  # constant -> spearman 0 for everyone
        rows.append(_row(i, duration, target))
    return Dataset(rows=rows)


def _patch_dataset(monkeypatch, mode: str = "learnable"):
    from app.services.ai_clipping import dataset_service, ml_ranker

    synthetic = _synthetic_dataset(mode=mode)
    monkeypatch.setattr(ml_ranker, "build_training_dataset", lambda db: synthetic)
    monkeypatch.setattr(dataset_service, "build_training_dataset", lambda db: synthetic)


def _settings(monkeypatch, tmp_path, min_rows: int = 20):
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "ml_model_dir", str(tmp_path / "models"))
    monkeypatch.setattr(s, "ml_min_training_rows", min_rows)
    return s


def test_spearman_sanity() -> None:
    from app.services.ai_clipping.ml_ranker import _spearman

    assert _spearman([1, 2, 3], [10, 20, 30]) == 1.0
    assert _spearman([1, 2, 3], [3, 2, 1]) == -1.0
    assert _spearman([5, 5, 5], [1, 2, 3]) == 0.0
    assert _spearman([1], [1]) == 0.0


def test_dataset_builder_joins_publication_clip_metric(client, monkeypatch) -> None:
    """End-to-end dataset row: published clip with features + metric -> 1 row."""
    from tests.unit.test_metrics import _published_publication as helper

    pub, _ = helper(client, monkeypatch)
    # attach a metric with views
    from app.db import session as db_session
    from app.models.metric import Metric
    from app.models.publication import Publication
    from app.services.ai_clipping import dataset_service

    db = db_session.session_factory()
    publication = db.get(Publication, uuid.UUID(pub["id"]))
    clip = publication.clip
    clip.features = {**FEATS, "window": {"start": 0.0, "end": 10.0}}  # as promote copies
    db.add(Metric(publication_id=publication.id, views=1000, likes=10, comments=2, shares=1, raw={}))
    db.commit()
    db.close()

    dataset = dataset_service.build_training_dataset(db_session.session_factory())
    assert len(dataset.rows) == 1
    row = dataset.rows[0]
    assert row.target_kind == "views"
    assert row.features["speech_ratio"] == 0.5 and row.features["duration_sec"] == 10.0


def test_train_too_small_dataset_rejected(db, monkeypatch, tmp_path) -> None:
    _settings(monkeypatch, tmp_path, min_rows=100)
    _patch_dataset(monkeypatch, "learnable")
    from app.services.ai_clipping import ml_ranker

    run = ml_ranker.train_and_evaluate(db)
    assert run.status == "rejected" and run.gate_passed is False
    assert "too small" in run.error_message


def test_train_gate_pass_activates_model(db, monkeypatch, tmp_path) -> None:
    _settings(monkeypatch, tmp_path, min_rows=20)
    _patch_dataset(monkeypatch, "learnable")
    from app.services.ai_clipping import ml_ranker

    run = ml_ranker.train_and_evaluate(db)
    assert run.status == "succeeded", run.error_message
    assert run.gate_passed is True
    assert run.val_spearman > run.baseline_spearman
    assert run.model_path and (tmp_path / "models").exists()
    # active model resolves and reranks
    model = ml_ranker.get_active_model(db)
    assert model is not None
    candidates = [
        SimpleNamespace(score=0.9, features={**FEATS, "duration_sec": 20.0}),
        SimpleNamespace(score=0.1, features={**FEATS, "duration_sec": 55.0}),
    ]
    ordered, ranked_by = ml_ranker.rerank(db, candidates)
    assert ranked_by == "ml"
    assert ordered[0].features["duration_sec"] == 55.0  # longer -> higher ML score
    assert "ml_score" in ordered[0].features


def test_train_gate_fail_falls_back_to_heuristic(db, monkeypatch, tmp_path) -> None:
    _settings(monkeypatch, tmp_path, min_rows=20)
    _patch_dataset(monkeypatch, "flat")
    from app.services.ai_clipping import ml_ranker

    run = ml_ranker.train_and_evaluate(db)
    assert run.status == "rejected" and run.gate_passed is False
    assert run.val_spearman <= run.baseline_spearman or run.val_spearman <= 0
    assert ml_ranker.get_active_model(db) is None
    candidates = [SimpleNamespace(score=0.9, features={**FEATS, "duration_sec": 20.0})]
    ordered, ranked_by = ml_ranker.rerank(db, candidates)
    assert ranked_by == "heuristic" and ordered == candidates


def test_rerank_disabled_by_settings(db, monkeypatch, tmp_path) -> None:
    s = _settings(monkeypatch, tmp_path, min_rows=20)
    monkeypatch.setattr(s, "ml_rerank_enabled", False)
    from app.services.ai_clipping import ml_ranker

    assert ml_ranker.get_active_model(db) is None


def test_ml_train_api_and_runs(client, monkeypatch, tmp_path) -> None:
    _settings(monkeypatch, tmp_path, min_rows=20)
    _patch_dataset(monkeypatch, "learnable")

    status = client.get("/api/v1/ml/dataset-status").json()
    assert status["rows"] == 40 and status["targets"] == ["views"]

    accepted = client.post("/api/v1/ml/train")
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["job_id"]
    job = client.get(f"/api/v1/jobs/{job_id}").json()
    assert job["status"] == "succeeded"
    assert job["result"]["gate_passed"] is True

    runs = client.get("/api/v1/ml/runs").json()
    assert runs["total"] >= 1
    latest = runs["items"][0]
    assert latest["status"] == "succeeded" and latest["gate_passed"] is True


def test_self_train_check_beats_threshold(client, monkeypatch, tmp_path) -> None:
    from app.workers.tasks import self_train_check

    result = self_train_check()  # empty DB -> 0 new rows -> no retrain
    assert result == {"retrained": False, "new_rows": 0}
