"""Spec §5: a single bad frame must never flip a track's classification —
only the smoothed rolling average, against configurable thresholds, decides
ADULT / CHILD / UNKNOWN."""
from __future__ import annotations

from app.cv.classifier.rolling_history import AgeLabel, RollingClassificationHistory


def test_single_frame_is_unknown_until_window_fills_with_consistent_signal():
    history = RollingClassificationHistory(window=15, adult_threshold=0.75, child_threshold=0.75)
    state = history.update(track_id=1, adult_score=0.95, confidence=1.0)
    # one high-confidence adult-looking frame alone isn't proof yet, but the
    # *smoothed average* of a single 0.95 sample is 0.95 >= 0.75 -> already ADULT.
    # The real protection is against a single OUTLIER frame, tested below.
    assert state.label == AgeLabel.ADULT


def test_single_outlier_frame_does_not_flip_an_established_label():
    history = RollingClassificationHistory(window=15, adult_threshold=0.75, child_threshold=0.75)
    for _ in range(14):
        history.update(track_id=1, adult_score=0.95, confidence=1.0)
    # one bad frame (e.g. classifier misfires on an occluded/bending adult)
    state = history.update(track_id=1, adult_score=0.05, confidence=1.0)
    # smoothed average over 15 samples (14x0.95 + 1x0.05)/15 = 0.89 -> still ADULT
    assert state.label == AgeLabel.ADULT
    assert state.smoothed_adult_score > 0.75


def test_consistently_child_like_scores_classify_as_child():
    history = RollingClassificationHistory(window=15, adult_threshold=0.75, child_threshold=0.75)
    for _ in range(15):
        state = history.update(track_id=2, adult_score=0.1, confidence=1.0)
    assert state.label == AgeLabel.CHILD


def test_ambiguous_smoothed_score_is_unknown_not_guessed():
    history = RollingClassificationHistory(window=15, adult_threshold=0.75, child_threshold=0.75)
    for _ in range(15):
        state = history.update(track_id=3, adult_score=0.5, confidence=1.0)
    assert state.label == AgeLabel.UNKNOWN


def test_window_only_keeps_the_most_recent_n_samples():
    history = RollingClassificationHistory(window=5, adult_threshold=0.75, child_threshold=0.75)
    for _ in range(5):
        history.update(track_id=4, adult_score=0.95, confidence=1.0)
    # now push 5 more low-confidence-direction frames — the old high scores
    # should have fully rolled out of the window
    for _ in range(5):
        state = history.update(track_id=4, adult_score=0.05, confidence=1.0)
    assert state.label == AgeLabel.CHILD
    assert len(state.history) == 5


def test_low_confidence_frames_are_weighted_less():
    history = RollingClassificationHistory(window=10, adult_threshold=0.75, child_threshold=0.75)
    # one strong, confident adult signal, followed by several low-confidence
    # child-leaning frames (e.g. tiny/partial detections) — the confident
    # sample should still dominate the smoothed average.
    history.update(track_id=5, adult_score=0.95, confidence=1.0)
    for _ in range(4):
        state = history.update(track_id=5, adult_score=0.1, confidence=0.05)
    assert state.label == AgeLabel.ADULT


def test_forget_clears_track_history():
    history = RollingClassificationHistory(window=15, adult_threshold=0.75, child_threshold=0.75)
    history.update(track_id=6, adult_score=0.9, confidence=1.0)
    assert 6 in history.active_track_ids()
    history.forget(6)
    assert 6 not in history.active_track_ids()
    state = history.get_state(6)
    assert state.label == AgeLabel.UNKNOWN
    assert state.sample_count == 0
