"""Heuristic ranker + features unit tests (deterministic, no media)."""
from app.core.config import get_settings
from app.services.ai_clipping.features import (
    KEY_PHRASES, Window, key_phrase_score, position_score, scene_alignment_score,
    speech_ratio, tempo_score, tempo_wpm,
)
from app.services.ai_clipping.heuristic_ranker import generate_windows, iou, rank_candidates
from app.services.transcription import scene_service

SEGS = [
    {"start": 0.0, "end": 5.0, "text": "смотри тут главное правило монтажа клипов"},
    {"start": 5.0, "end": 10.0, "text": "и вот секрет который мало кто знает"},
    {"start": 30.0, "end": 40.0, "text": "обычная речь без маркеров просто текст"},
    {"start": 100.0, "end": 110.0, "text": "итак подведём итог и главный вопрос"},
]


def test_key_phrases_ru_en_present() -> None:
    for phrase in ("смотри", "главное", "секрет", "how", "why", "secret"):
        assert phrase in KEY_PHRASES


def test_speech_ratio() -> None:
    assert speech_ratio(Window(0, 10), SEGS) == 1.0
    assert speech_ratio(Window(0, 20), SEGS[:2]) == 0.5
    assert speech_ratio(Window(50, 60), SEGS) == 0.0


def test_key_phrase_score_window_with_markers() -> None:
    with_markers = key_phrase_score(Window(0, 10), SEGS)
    without = key_phrase_score(Window(30, 40), SEGS)
    assert with_markers > without
    assert without == 0.0


def test_tempo() -> None:
    wpm = tempo_wpm(Window(0, 10), SEGS[:1])  # 8 words / 10s = 48 wpm
    assert 0 < wpm < 120
    assert tempo_score(Window(0, 10), SEGS[:1]) < 1.0
    # dense speech ~150 wpm => optimal
    dense = [{"start": 0, "end": 60, "text": " ".join(["слово"] * 150)}]
    assert 120 <= tempo_wpm(Window(0, 60), dense) <= 180
    assert tempo_score(Window(0, 60), dense) == 1.0


def test_position_intro_bonus_and_end_penalty() -> None:
    assert position_score(Window(0, 30), 100.0) == 1.0
    assert position_score(Window(95, 100), 100.0) == 0.3
    assert position_score(Window(40, 70), 100.0) == 0.5


def test_scene_alignment() -> None:
    boundaries = [0.0, 30.0, 60.0]
    assert scene_alignment_score(Window(0, 30), boundaries) == 1.0
    assert scene_alignment_score(Window(13, 43), boundaries) < 1.0
    assert scene_alignment_score(Window(10, 40), []) == 0.5  # neutral without scenes


def test_generate_windows_steps_and_lengths() -> None:
    windows = generate_windows(70.0)
    lengths = sorted({round(w.duration, 1) for w in windows})
    assert lengths == [15.0, 30.0, 45.0, 60.0]
    starts_30 = sorted(w.start for w in windows if w.duration == 30.0)
    assert starts_30 == [0.0, 5.0, 10.0, ..., 40.0] or starts_30[0] == 0.0 and starts_30[-1] == 40.0


def test_iou() -> None:
    assert iou(Window(0, 30), Window(0, 30)) == 1.0
    assert abs(iou(Window(0, 30), Window(15, 45)) - 15 / 45) < 1e-9
    assert iou(Window(0, 10), Window(20, 30)) == 0.0


def test_rank_candidates_deterministic_top() -> None:
    args = (120.0, SEGS, [0.0, 30.0, 60.0, 90.0], None)
    first = rank_candidates(*args, top_k=5)
    second = rank_candidates(*args, top_k=5)
    assert [(c.start, c.end, c.score) for c in first] == [(c.start, c.end, c.score) for c in second]
    assert len(first) == 5
    scores = [c.score for c in first]
    assert scores == sorted(scores, reverse=True)


def test_rank_candidates_nms_removes_overlaps() -> None:
    ranked = rank_candidates(120.0, SEGS, [0.0, 30.0, 60.0, 90.0], None, top_k=10)
    for i, a in enumerate(ranked):
        for b in ranked[i + 1:]:
            assert iou(Window(a.start, a.end), Window(b.start, b.end)) <= 0.5


def test_rank_candidates_weights_configurable(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_weights_speech", 1.0)
    monkeypatch.setattr(get_settings(), "ai_weights_keywords", 0.0)
    monkeypatch.setattr(get_settings(), "ai_weights_tempo", 0.0)
    monkeypatch.setattr(get_settings(), "ai_weights_loudness", 0.0)
    monkeypatch.setattr(get_settings(), "ai_weights_scene", 0.0)
    ranked = rank_candidates(120.0, SEGS, [0.0, 60.0], None, top_k=3)
    # speech-only weights => windows with most speech coverage must lead
    assert ranked[0].score == ranked[0].features["speech_ratio"]


def test_uniform_fallback_boundaries() -> None:
    assert scene_service.uniform_fallback_boundaries(95.0) == [30.0, 60.0, 90.0]
    assert scene_service.uniform_fallback_boundaries(10.0) == []
    assert scene_service.uniform_fallback_boundaries(0) == []
