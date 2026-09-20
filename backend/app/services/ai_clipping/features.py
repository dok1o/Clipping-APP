"""Window features for heuristic candidate scoring (master spec §18).

All features are pure functions of (window, transcript, scenes, loudness) —
deterministic and unit-testable without any media files.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Key-phrase markers (RU + EN), master spec §18; extend here (single source).
KEY_PHRASES_RU = [
    "смотри", "главное", "секрет", "ошибка", "вопрос", "давай", "итак",
    "запомни", "важно", "никогда", "итог", "проще",
]
KEY_PHRASES_EN = [
    "how", "what", "why", "secret", "mistake", "error", "listen", "look",
    "important", "key", "tip", "hack", "never", "always", "imagine",
]
KEY_PHRASES = KEY_PHRASES_RU + KEY_PHRASES_EN

TEMPO_OPTIMAL_WPM = (120.0, 180.0)  # bell curve peak range (spec §18)
INTRO_BONUS_SEC = 30.0  # intro window bonus (spec §18: интро 0-30с)
SCENE_ALIGN_TOLERANCE_SEC = 2.0


@dataclass(frozen=True)
class Window:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def speech_ratio(window: Window, segments: list[dict]) -> float:
    """Fraction of the window covered by speech segments (0..1)."""
    if not segments or window.duration <= 0:
        return 0.0
    covered = sum(_overlap(window.start, window.end, s["start"], s["end"]) for s in segments)
    return min(covered / window.duration, 1.0)


def _window_words(window: Window, segments: list[dict]) -> list[str]:
    words: list[str] = []
    for seg in segments:
        if _overlap(window.start, window.end, seg["start"], seg["end"]) > 0:
            words.extend(seg.get("text", "").split())
    return words


def key_phrase_score(window: Window, segments: list[dict]) -> float:
    """Marker phrases per word, normalized to a 0..1-ish score."""
    words = _window_words(window, segments)
    if not words:
        return 0.0
    text = " " + " ".join(w.lower().strip(".,!?;:«»\"'()") for w in words) + " "
    hits = sum(1 for phrase in KEY_PHRASES if f" {phrase} " in text)
    return min(hits / 3.0, 1.0)  # 3+ marker hits => full score


def tempo_wpm(window: Window, segments: list[dict]) -> float:
    words = _window_words(window, segments)
    minutes = window.duration / 60.0
    return (len(words) / minutes) if minutes > 0 else 0.0


def tempo_score(window: Window, segments: list[dict]) -> float:
    """Bell curve around the optimal 120-180 WPM range."""
    wpm = tempo_wpm(window, segments)
    low, high = TEMPO_OPTIMAL_WPM
    if wpm == 0:
        return 0.0
    if low <= wpm <= high:
        return 1.0
    distance = (low - wpm) if wpm < low else (wpm - high)
    return max(0.0, 1.0 - distance / max(low, 1.0))


def loudness_score(window: Window, rms_timeline: list[tuple[float, float]] | None) -> float:
    """Mean RMS (per-second timeline [(sec, rms)]) normalized 0..1; neutral 0.5 if unknown."""
    if not rms_timeline:
        return 0.5
    values = [rms for sec, rms in rms_timeline if window.start <= sec < window.end]
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return min(mean / 20000.0, 1.0)  # 16-bit PCM RMS; ~20k ≈ loud speech


def position_score(window: Window, video_duration: float | None) -> float:
    """Intro (0-30s) bonus; slight penalty for the very end; neutral otherwise."""
    if window.start < INTRO_BONUS_SEC:
        return 1.0
    if video_duration and window.end > video_duration - 5.0:
        return 0.3
    return 0.5


def scene_alignment_score(window: Window, boundaries: list[float]) -> float:
    """1.0 when both window edges sit near scene boundaries, partial otherwise."""
    if not boundaries:
        return 0.5
    def near(edge: float) -> float:
        best = min((abs(edge - b) for b in boundaries), default=999.0)
        return 1.0 if best <= SCENE_ALIGN_TOLERANCE_SEC else max(0.0, 1.0 - best / 10.0)
    return (near(window.start) + near(window.end)) / 2.0


def compute_features(
    window: Window,
    segments: list[dict],
    boundaries: list[float],
    rms_timeline: list[tuple[float, float]] | None,
    video_duration: float | None,
) -> dict:
    return {
        "window": {"start": window.start, "end": window.end},
        "speech_ratio": round(speech_ratio(window, segments), 4),
        "key_phrases": round(key_phrase_score(window, segments), 4),
        "tempo_wpm": round(tempo_wpm(window, segments), 1),
        "tempo_score": round(tempo_score(window, segments), 4),
        "loudness": round(loudness_score(window, rms_timeline), 4),
        "position": round(position_score(window, video_duration), 4),
        "scene_alignment": round(scene_alignment_score(window, boundaries), 4),
    }
