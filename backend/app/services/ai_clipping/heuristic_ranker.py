"""Heuristic candidate ranking: sliding windows -> weighted score -> NMS -> top_k.

Weights come from AI_WEIGHTS_* env (configurable, spec §18). No ML here —
Stage 3 is strictly heuristic; ml_ranker (Stage 7) reuses the same features.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings
from app.services.ai_clipping.features import Window, compute_features

WINDOW_LENGTHS_SEC = (15.0, 30.0, 45.0, 60.0)
STEP_SEC = 5.0
NMS_IOU_THRESHOLD = 0.5


@dataclass(frozen=True)
class RankedCandidate:
    start: float
    end: float
    score: float
    features: dict
    reason: str


def iou(a: Window, b: Window) -> float:
    inter = max(0.0, min(a.end, b.end) - max(a.start, b.start))
    union = (a.end - a.start) + (b.end - b.start) - inter
    return inter / union if union > 0 else 0.0


def generate_windows(duration_sec: float) -> list[Window]:
    windows: list[Window] = []
    for length in WINDOW_LENGTHS_SEC:
        start = 0.0
        while start + length <= duration_sec:
            windows.append(Window(round(start, 3), round(start + length, 3)))
            start += STEP_SEC
    return windows


def _weights() -> dict[str, float]:
    settings = get_settings()
    return {
        "speech": settings.ai_weights_speech,
        "keywords": settings.ai_weights_keywords,
        "tempo": settings.ai_weights_tempo,
        "loudness": settings.ai_weights_loudness,
        "scene": settings.ai_weights_scene,
    }


def score_window(
    window: Window,
    segments: list[dict],
    boundaries: list[float],
    rms_timeline: list[tuple[float, float]] | None,
    video_duration: float | None,
    weights: dict[str, float] | None = None,
) -> tuple[float, dict, str]:
    features = compute_features(window, segments, boundaries, rms_timeline, video_duration)
    weights = weights or _weights()
    score = (
        weights["speech"] * features["speech_ratio"]
        + weights["keywords"] * features["key_phrases"]
        + weights["tempo"] * features["tempo_score"]
        + weights["loudness"] * features["loudness"]
        + weights["scene"] * features["scene_alignment"]
    )
    top = sorted(
        (
            ("речь", features["speech_ratio"]), ("маркеры", features["key_phrases"]),
            ("темп", features["tempo_score"]), ("громкость", features["loudness"]),
            ("сцены", features["scene_alignment"]),
        ),
        key=lambda kv: kv[1],
        reverse=True,
    )[:2]
    reason = f"топ-факторы: {top[0][0]}={top[0][1]:.2f}, {top[1][0]}={top[1][1]:.2f}; " \
              f"окно {window.start:.0f}-{window.end:.0f}с"
    return round(score, 4), features, reason


def rank_candidates(
    duration_sec: float,
    segments: list[dict],
    boundaries: list[float],
    rms_timeline: list[tuple[float, float]] | None,
    *,
    top_k: int = 5,
    weights: dict[str, float] | None = None,
) -> list[RankedCandidate]:
    """Sliding windows -> weighted heuristic score -> NMS(IoU>0.5) -> top_k."""
    scored: list[tuple[float, RankedCandidate]] = []
    for window in generate_windows(duration_sec):
        score, features, reason = score_window(
            window, segments, boundaries, rms_timeline, duration_sec, weights
        )
        scored.append((score, RankedCandidate(window.start, window.end, score, features, reason)))

    scored.sort(key=lambda item: item[0], reverse=True)

    selected: list[RankedCandidate] = []
    for score, candidate in scored:
        window = Window(candidate.start, candidate.end)
        if any(iou(window, Window(s.start, s.end)) > NMS_IOU_THRESHOLD for s in selected):
            continue
        selected.append(candidate)
        if len(selected) >= top_k:
            break
    return selected
