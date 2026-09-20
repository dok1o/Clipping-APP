"""Training dataset builder (spec §3.6): clip features -> outcome.

Row = published Clip (promoted from a candidate => features copied) joined with
its LATEST metric snapshot. Target = log1p(views) (fallback: weighted engagement).
Only rows with a real platform outcome are used — no synthetic labels.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.metric import Metric
from app.models.publication import Publication, PublicationStatus

# keys as produced by features.compute_features (Stage 3)
FEATURE_KEYS = (
    "speech_ratio", "key_phrases", "tempo_wpm", "tempo_score",
    "loudness", "position", "scene_alignment",
)


@dataclass(frozen=True)
class LabeledRow:
    clip_id: UUID
    publication_id: UUID
    platform: str
    captured_at: datetime
    features: dict[str, float]
    target: float
    target_kind: str  # "views" | "engagement"


@dataclass
class Dataset:
    rows: list[LabeledRow] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)

    def __len__(self) -> int:  # pragma: no cover
        return len(self.rows)


def _target_from_metric(metric: Metric) -> tuple[float, str] | None:
    if metric.views is not None:
        return math.log1p(metric.views), "views"
    likes, comments, shares = metric.likes or 0, metric.comments or 0, metric.shares or 0
    if likes or comments or shares:
        return math.log1p(likes * 3 + comments * 5 + shares * 4), "engagement"
    return None


def _feature_vector(features: dict[str, Any] | None) -> dict[str, float] | None:
    if not features:
        return None
    vector = {}
    for key in FEATURE_KEYS:
        value = features.get(key)
        if not isinstance(value, (int, float)):
            return None  # a promoted candidate must carry the full feature set
        vector[key] = float(value)
    window = features.get("window") or {}
    try:
        vector["duration_sec"] = float(window.get("end", 0.0)) - float(window.get("start", 0.0))
    except (TypeError, ValueError):
        vector["duration_sec"] = 0.0
    return vector


def build_training_dataset(db: Session) -> Dataset:
    dataset = Dataset()
    publications = db.scalars(
        select(Publication).where(
            Publication.status == PublicationStatus.PUBLISHED,
            Publication.external_post_id.is_not(None),
        ).order_by(Publication.published_at)
    )
    for publication in publications:
        clip = publication.clip
        if clip is None:
            dataset.skipped["no_clip"] = dataset.skipped.get("no_clip", 0) + 1
            continue
        metric = db.scalars(
            select(Metric).where(Metric.publication_id == publication.id)
            .order_by(Metric.captured_at.desc()).limit(1)
        ).first()
        if metric is None:
            dataset.skipped["no_metrics"] = dataset.skipped.get("no_metrics", 0) + 1
            continue
        target = _target_from_metric(metric)
        if target is None:
            dataset.skipped["empty_metric"] = dataset.skipped.get("empty_metric", 0) + 1
            continue
        vector = _feature_vector(clip.features)
        if vector is None:
            dataset.skipped["no_features"] = dataset.skipped.get("no_features", 0) + 1
            continue
        dataset.rows.append(LabeledRow(
            clip_id=clip.id,
            publication_id=publication.id,
            platform=publication.platform,
            captured_at=metric.captured_at,
            features=vector,
            target=target[0],
            target_kind=target[1],
        ))
    return dataset
