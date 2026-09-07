"""Pure, framework-free supervision state machine — deterministic given a
sequence of (timestamp, children_present, adult_present) samples, so it can
be unit tested without a camera, a database, or any CV model at all.

Two-tier debouncing (spec §6/§7):

    adult disappears
          │
          ▼
    grace period (ADULT_GRACE_PERIOD_SECONDS) ── absorbed silently, state
          │                                       stays SUPERVISED
          ▼ (still absent)
    WAITING_FOR_ADULT ("potentially unsupervised", visible on the dashboard)
          │
          ▼ (absent for UNSUPERVISED_DELAY_SECONDS total)
    UNSUPERVISED ── one incident_id assigned here; stays UNSUPERVISED without
                     re-firing until the adult returns or the children leave.

Camera offline handling deliberately lives *outside* this class (see
ClassroomMonitor) — while a camera is offline nothing calls update(), so the
state simply freezes rather than drifting toward UNSUPERVISED on missing data.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum


class SupervisionState(str, Enum):
    EMPTY = "EMPTY"  # no children present — nothing to supervise
    SUPERVISED = "SUPERVISED"
    WAITING_FOR_ADULT = "WAITING_FOR_ADULT"  # "potentially unsupervised"
    UNSUPERVISED = "UNSUPERVISED"


@dataclass
class SupervisionUpdateResult:
    state: SupervisionState
    incident_id: str | None
    just_confirmed_unsupervised: bool = False
    just_resolved: bool = False
    resolution_reason: str | None = None
    seconds_without_adult: float = 0.0


@dataclass
class SupervisionStateMachine:
    classroom_id: str
    unsupervised_delay_seconds: float = 10.0
    adult_grace_period_seconds: float = 3.0

    state: SupervisionState = field(default=SupervisionState.EMPTY)
    _absence_started_at: float | None = field(default=None, repr=False)
    _incident_id: str | None = field(default=None, repr=False)

    def update(self, timestamp: float, children_present: bool, adult_present: bool) -> SupervisionUpdateResult:
        if not children_present:
            return self._handle_no_children(timestamp)

        if adult_present:
            return self._handle_adult_present(timestamp)

        return self._handle_adult_absent(timestamp)

    def _handle_no_children(self, timestamp: float) -> SupervisionUpdateResult:
        was_unsupervised = self.state == SupervisionState.UNSUPERVISED
        incident = self._incident_id
        self.state = SupervisionState.EMPTY
        self._absence_started_at = None
        self._incident_id = None
        return SupervisionUpdateResult(
            state=self.state,
            incident_id=incident,
            just_resolved=was_unsupervised,
            resolution_reason="children_left" if was_unsupervised else None,
        )

    def _handle_adult_present(self, timestamp: float) -> SupervisionUpdateResult:
        was_unsupervised = self.state == SupervisionState.UNSUPERVISED
        incident = self._incident_id
        self.state = SupervisionState.SUPERVISED
        self._absence_started_at = None
        if was_unsupervised:
            self._incident_id = None
        return SupervisionUpdateResult(
            state=self.state,
            incident_id=incident if was_unsupervised else self._incident_id,
            just_resolved=was_unsupervised,
            resolution_reason="adult_returned" if was_unsupervised else None,
        )

    def _handle_adult_absent(self, timestamp: float) -> SupervisionUpdateResult:
        if self._absence_started_at is None:
            self._absence_started_at = timestamp

        elapsed = timestamp - self._absence_started_at

        if self.state == SupervisionState.UNSUPERVISED:
            # already confirmed — do not re-fire, just keep reporting elapsed time
            return SupervisionUpdateResult(state=self.state, incident_id=self._incident_id, seconds_without_adult=elapsed)

        if elapsed < self.adult_grace_period_seconds:
            self.state = SupervisionState.SUPERVISED if self.state != SupervisionState.WAITING_FOR_ADULT else self.state
            return SupervisionUpdateResult(state=self.state, incident_id=None, seconds_without_adult=elapsed)

        if elapsed < self.unsupervised_delay_seconds:
            self.state = SupervisionState.WAITING_FOR_ADULT
            return SupervisionUpdateResult(state=self.state, incident_id=None, seconds_without_adult=elapsed)

        # confirmed unsupervised
        self.state = SupervisionState.UNSUPERVISED
        self._incident_id = f"INC-{uuid.uuid4().hex[:12]}"
        return SupervisionUpdateResult(
            state=self.state,
            incident_id=self._incident_id,
            just_confirmed_unsupervised=True,
            seconds_without_adult=elapsed,
        )
