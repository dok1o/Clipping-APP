"""ML reranker (Stage 7, spec §3.6): gradient boosting on tabular clip features.

- Train: time-ordered split (older rows train, newest val), Spearman on val.
- Eval gate: the model must beat the heuristic baseline on the SAME val rows
  (spearman_ml > spearman_heuristic) AND be positively correlated (> 0).
  Gate fail => run recorded as rejected, model NOT activated (heuristic stays).
- Inference: active model (latest gate_passed run, file exists, fresh enough)
  reranks heuristic candidates; ANY problem => heuristic order (fallback).
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import joblib
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.job import Job, JobStatus
from app.models.training_run import TrainingRun
from app.services.ai_clipping.dataset_service import FEATURE_KEYS, Dataset, build_training_dataset

logger = get_logger(__name__)

MODEL_PREFIX = "ml_rerank"

try:  # pragma: no cover - environment dependent
    import lightgbm as lgb

    def _make_model(seed: int):
        return lgb.LGBMRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            min_child_samples=5, subsample=0.9, colsample_bytree=0.9,
            random_state=seed, verbosity=-1,
        )

    _BACKEND = "lightgbm"
except ImportError:  # pragma: no cover
    from sklearn.ensemble import GradientBoostingRegressor

    def _make_model(seed: int):
        return GradientBoostingRegressor(
            n_estimators=200, max_depth=3, learning_rate=0.05,
            min_samples_leaf=2, random_state=seed,
        )

    _BACKEND = "sklearn-gbrt"


def _spearman(a: list[float], b: list[float]) -> float:
    """Spearman rank correlation (ties averaged) — no scipy dependency."""
    if len(a) != len(b) or len(a) < 2:
        return 0.0

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        rank = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                rank[order[k]] = avg
            i = j + 1
        return rank

    ra, rb = ranks(a), ranks(b)
    n = len(ra)
    mean_a = sum(ra) / n
    mean_b = sum(rb) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(ra, rb))
    var_a = sum((x - mean_a) ** 2 for x in ra)
    var_b = sum((y - mean_b) ** 2 for y in rb)
    if var_a == 0 or var_b == 0:
        return 0.0
    return cov / math.sqrt(var_a * var_b)


def _X(rows) -> list[list[float]]:
    keys = list(FEATURE_KEYS) + ["duration_sec"]
    return [[r.features[k] for k in keys] for r in rows]


def _heuristic_scores(rows) -> list[float]:
    """Heuristic baseline: exact mirror of heuristic_ranker.score_window formula."""
    from app.services.ai_clipping.heuristic_ranker import _weights

    w = _weights()
    return [
        w["speech"] * r.features["speech_ratio"]
        + w["keywords"] * r.features["key_phrases"]
        + w["tempo"] * r.features["tempo_score"]
        + w["loudness"] * r.features["loudness"]
        + w["scene"] * r.features["scene_alignment"]
        for r in rows
    ]


def train_and_evaluate(db: Session, job: Job | None = None) -> TrainingRun:
    """Build dataset, train, gate-evaluate, persist model + TrainingRun row."""
    settings = get_settings()
    dataset: Dataset = build_training_dataset(db)
    run = TrainingRun(status="failed", n_rows=len(dataset), details={"backend": _BACKEND})
    db.add(run)

    if len(dataset) < settings.ml_min_training_rows:
        run.status = "rejected"
        run.error_message = (
            f"dataset too small: {len(dataset)} < ml_min_training_rows={settings.ml_min_training_rows}"
        )
        db.commit()
        db.refresh(run)
        return run

    rows = sorted(dataset.rows, key=lambda r: r.captured_at)
    n_val = max(3, int(len(rows) * settings.ml_val_fraction))
    train_rows, val_rows = rows[:-n_val], rows[-n_val:]

    model = _make_model(seed=42)
    model.fit(_X(train_rows), [r.target for r in train_rows])
    predictions = [float(p) for p in model.predict(_X(val_rows))]
    targets = [r.target for r in val_rows]

    val_spearman = _spearman(predictions, targets)
    baseline = _spearman(_heuristic_scores(val_rows), targets)
    gate = val_spearman > baseline and val_spearman > 0.0

    run.val_spearman = round(val_spearman, 4)
    run.baseline_spearman = round(baseline, 4)
    run.gate_passed = gate
    run.details = {
        "backend": _BACKEND,
        "n_train": len(train_rows),
        "n_val": len(val_rows),
        "targets": sorted({r.target_kind for r in rows}),
        "feature_keys": list(FEATURE_KEYS) + ["duration_sec"],
    }

    if gate:
        model_dir = Path(settings.ml_model_dir)
        model_dir.mkdir(parents=True, exist_ok=True)
        version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        model_path = model_dir / f"{MODEL_PREFIX}_{version}.joblib"
        joblib.dump({"model": model, "feature_keys": list(FEATURE_KEYS) + ["duration_sec"],
                     "backend": _BACKEND, "version": version}, model_path)
        run.status = "succeeded"
        run.model_version = version
        run.model_path = str(model_path)
        if job is not None:
            job.result = {"training_run_id": str(run.id), "model_version": version,
                          "val_spearman": run.val_spearman,
                          "baseline_spearman": run.baseline_spearman,
                          "gate_passed": True}
    else:
        run.status = "rejected"
        run.error_message = (
            f"eval gate failed: ml spearman {val_spearman:.3f} vs heuristic {baseline:.3f}"
        )
        if job is not None:
            job.result = {"training_run_id": str(run.id), "gate_passed": False,
                          "val_spearman": run.val_spearman,
                          "baseline_spearman": run.baseline_spearman}
    db.commit()
    db.refresh(run)
    logger.info("ml train run=%s status=%s ml=%.3f baseline=%.3f",
                run.id, run.status, val_spearman, baseline)
    return run


def get_active_model(db: Session) -> tuple[Any, dict] | None:
    """Latest gate_passed run with an existing, fresh model file — else None."""
    settings = get_settings()
    if not settings.ml_rerank_enabled:
        return None
    run = db.scalars(
        select(TrainingRun)
        .where(TrainingRun.status == "succeeded", TrainingRun.gate_passed.is_(True))
        .order_by(TrainingRun.created_at.desc())
        .limit(1)
    ).first()
    if run is None or not run.model_path or not Path(run.model_path).exists():
        return None
    age_days = (datetime.now(timezone.utc) - run.created_at.replace(tzinfo=timezone.utc)).days
    if age_days > settings.ml_max_age_days:
        return None  # stale -> heuristic fallback
    bundle = joblib.load(run.model_path)
    return bundle["model"], bundle


def rerank(db: Session, candidates: list) -> tuple[list, str]:
    """Rerank heuristic candidates by ML score; fallback to heuristic order.

    candidates: objects with .score (heuristic) and .features (dict).
    Returns (ordered_list, ranked_by) where ranked_by is "ml" or "heuristic".
    """
    model = None
    try:
        loaded = get_active_model(db)
        model = loaded[0] if loaded else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("ml rerank unavailable, heuristic fallback: %s", exc)
        model = None
    if model is None or not candidates:
        return list(candidates), "heuristic"

    keys = list(FEATURE_KEYS) + ["duration_sec"]
    try:
        matrix = []
        for c in candidates:
            features = c.features or {}
            matrix.append([float(features.get(k, 0.0)) for k in keys])
        scores = [float(s) for s in model.predict(matrix)]
    except Exception as exc:  # noqa: BLE001
        logger.warning("ml rerank predict failed, heuristic fallback: %s", exc)
        return list(candidates), "heuristic"

    paired = sorted(zip(candidates, scores), key=lambda p: p[1], reverse=True)
    ordered = []
    for candidate, ml_score in paired:
        try:
            candidate.features = {**candidate.features, "ml_score": round(ml_score, 4)}
        except Exception:  # pragma: no cover
            pass
        ordered.append(candidate)
    return ordered, "ml"


def count_rows_for_retrain(db: Session) -> int:
    dataset = build_training_dataset(db)
    last = db.scalars(
        select(TrainingRun).order_by(TrainingRun.created_at.desc()).limit(1)
    ).first()
    if last is None:
        return len(dataset)
    cutoff = last.created_at.replace(tzinfo=timezone.utc)
    return sum(1 for r in dataset.rows if r.captured_at.replace(tzinfo=timezone.utc) > cutoff)
