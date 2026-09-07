"""Covers spec §30 test cases 1,2,3,4,5,7,8 at the pure state-machine level
(no camera, no models, no DB — fully deterministic on simulated timestamps).
Case 6 (camera offline) is covered in test_classroom_monitor.py since it
requires the ClassroomMonitor wrapper, not the bare state machine.
"""
from __future__ import annotations

from app.supervision.state_machine import SupervisionState, SupervisionStateMachine

GRACE = 3.0
DELAY = 10.0


def make_sm() -> SupervisionStateMachine:
    return SupervisionStateMachine("class-1", unsupervised_delay_seconds=DELAY, adult_grace_period_seconds=GRACE)


def test_case1_adult_and_children_supervised():
    sm = make_sm()
    result = sm.update(timestamp=0, children_present=True, adult_present=True)
    assert result.state == SupervisionState.SUPERVISED
    assert result.incident_id is None


def test_case2_children_only_briefly_no_alert():
    sm = make_sm()
    sm.update(timestamp=0, children_present=True, adult_present=True)
    # adult disappears; children remain, but only for 3 seconds — within grace period
    r1 = sm.update(timestamp=1, children_present=True, adult_present=False)
    r2 = sm.update(timestamp=2.9, children_present=True, adult_present=False)
    assert r1.state == SupervisionState.SUPERVISED
    assert r2.state == SupervisionState.SUPERVISED
    assert r1.incident_id is None and r2.incident_id is None


def test_case3_children_only_over_10s_triggers_alert():
    sm = make_sm()
    sm.update(timestamp=0, children_present=True, adult_present=True)
    sm.update(timestamp=0.1, children_present=True, adult_present=False)  # adult disappears
    r_grace = sm.update(timestamp=2, children_present=True, adult_present=False)
    assert r_grace.state == SupervisionState.SUPERVISED  # still inside grace period

    r_waiting = sm.update(timestamp=5, children_present=True, adult_present=False)
    assert r_waiting.state == SupervisionState.WAITING_FOR_ADULT
    assert r_waiting.incident_id is None  # not confirmed yet — no alert

    r_confirmed = sm.update(timestamp=10.2, children_present=True, adult_present=False)
    assert r_confirmed.state == SupervisionState.UNSUPERVISED
    assert r_confirmed.just_confirmed_unsupervised is True
    assert r_confirmed.incident_id is not None


def test_case4_adult_returns_auto_resolves():
    sm = make_sm()
    sm.update(timestamp=0, children_present=True, adult_present=True)
    sm.update(timestamp=0.1, children_present=True, adult_present=False)
    r_confirmed = sm.update(timestamp=10.2, children_present=True, adult_present=False)
    assert r_confirmed.state == SupervisionState.UNSUPERVISED
    incident = r_confirmed.incident_id

    r_returned = sm.update(timestamp=15, children_present=True, adult_present=True)
    assert r_returned.state == SupervisionState.SUPERVISED
    assert r_returned.just_resolved is True
    assert r_returned.resolution_reason == "adult_returned"
    assert r_returned.incident_id == incident


def test_case5_adult_briefly_occluded_no_alert():
    sm = make_sm()
    sm.update(timestamp=0, children_present=True, adult_present=True)
    # occlusion for 1.5s — well inside the grace period
    sm.update(timestamp=1, children_present=True, adult_present=False)
    r = sm.update(timestamp=1.5, children_present=True, adult_present=True)
    assert r.state == SupervisionState.SUPERVISED
    assert r.just_resolved is False  # nothing to resolve — never left SUPERVISED visibly


def test_case7_single_frame_flip_does_not_confirm_unsupervised():
    """Even if the classifier momentarily mis-flags the only adult as a
    child for a single frame (i.e. adult_present flips false for one
    sample), a single sample under the grace period must not change state
    or create an incident."""
    sm = make_sm()
    sm.update(timestamp=0, children_present=True, adult_present=True)
    r = sm.update(timestamp=0.2, children_present=True, adult_present=False)
    assert r.state == SupervisionState.SUPERVISED
    assert r.incident_id is None
    r2 = sm.update(timestamp=0.4, children_present=True, adult_present=True)
    assert r2.state == SupervisionState.SUPERVISED
    assert r2.just_resolved is False


def test_case8_multiple_classrooms_are_independent():
    sm_a = make_sm()
    sm_b = make_sm()

    sm_a.update(timestamp=0, children_present=True, adult_present=False)
    sm_b.update(timestamp=0, children_present=True, adult_present=True)

    r_a = sm_a.update(timestamp=10.1, children_present=True, adult_present=False)
    r_b = sm_b.update(timestamp=10.1, children_present=True, adult_present=True)

    assert r_a.state == SupervisionState.UNSUPERVISED
    assert r_b.state == SupervisionState.SUPERVISED


def test_no_duplicate_alerts_while_unsupervised_persists():
    sm = make_sm()
    sm.update(timestamp=0, children_present=True, adult_present=False)
    r1 = sm.update(timestamp=10.1, children_present=True, adult_present=False)
    assert r1.just_confirmed_unsupervised is True
    incident = r1.incident_id

    # remains unsupervised for a long time — must not re-fire or change incident_id
    for t in (30, 60, 120, 300):
        r = sm.update(timestamp=t, children_present=True, adult_present=False)
        assert r.just_confirmed_unsupervised is False
        assert r.incident_id == incident


def test_new_incident_after_resolve_then_absent_again():
    sm = make_sm()
    sm.update(timestamp=0, children_present=True, adult_present=False)
    r1 = sm.update(timestamp=10.1, children_present=True, adult_present=False)
    incident1 = r1.incident_id

    sm.update(timestamp=15, children_present=True, adult_present=True)  # adult returns, resolves

    sm.update(timestamp=20, children_present=True, adult_present=False)  # adult leaves again
    r2 = sm.update(timestamp=30.1, children_present=True, adult_present=False)
    assert r2.just_confirmed_unsupervised is True
    assert r2.incident_id != incident1


def test_children_leaving_resolves_active_incident():
    sm = make_sm()
    sm.update(timestamp=0, children_present=True, adult_present=False)
    r1 = sm.update(timestamp=10.1, children_present=True, adult_present=False)
    assert r1.state == SupervisionState.UNSUPERVISED

    r2 = sm.update(timestamp=11, children_present=False, adult_present=False)
    assert r2.state == SupervisionState.EMPTY
    assert r2.just_resolved is True
    assert r2.resolution_reason == "children_left"
