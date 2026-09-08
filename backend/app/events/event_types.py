from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    UNSUPERVISED_DETECTED = "UNSUPERVISED_DETECTED"
    ALERT_CREATED = "ALERT_CREATED"
    ALERT_ACKNOWLEDGED = "ALERT_ACKNOWLEDGED"
    ALERT_RESOLVED = "ALERT_RESOLVED"
    BUZZER_TRIGGERED = "BUZZER_TRIGGERED"
    BUZZER_CLEARED = "BUZZER_CLEARED"
    SUPERVISION_RESTORED = "SUPERVISION_RESTORED"  # internal signal consumed by AlertManager to resolve an alert
    CAMERA_OFFLINE = "CAMERA_OFFLINE"
    CAMERA_ONLINE = "CAMERA_ONLINE"
    CLASSROOM_STATUS_CHANGED = "CLASSROOM_STATUS_CHANGED"
    TRACKED_STATE_UPDATE = "TRACKED_STATE_UPDATE"  # per-frame debug/live overlay payload
    PERSON_ENTERED = "PERSON_ENTERED"  # a tracked person crossed the gate line into the classroom
    PERSON_EXITED = "PERSON_EXITED"  # a tracked person crossed the gate line out of the classroom
