import type { Alert } from './alert';
import type { SupervisionStatus } from './classroom';

export type EventType =
  | 'ALERT_CREATED'
  | 'ALERT_ACKNOWLEDGED'
  | 'ALERT_RESOLVED'
  | 'BUZZER_TRIGGERED'
  | 'BUZZER_CLEARED'
  | 'CAMERA_OFFLINE'
  | 'CAMERA_ONLINE'
  | 'CLASSROOM_STATUS_CHANGED'
  | 'TRACKED_STATE_UPDATE';

export interface TrackedPerson {
  track_id: number;
  box: [number, number, number, number];
  label: 'ADULT' | 'CHILD' | 'UNKNOWN';
  confidence: number;
  in_roi: boolean;
}

export interface TrackedStateUpdatePayload {
  camera_id: string;
  classroom_id: string;
  state: SupervisionStatus;
  adult_count: number;
  child_count: number;
  unknown_count: number;
  people: TrackedPerson[];
  fps: number;
  inference_ms: number;
  timestamp: string;
}

export interface ClassroomStatusChangedPayload {
  camera_id: string;
  classroom_id: string;
  state: SupervisionStatus;
  children_count: number;
  adult_count: number;
  unknown_count: number;
  timestamp: string;
}

export interface CameraLinkPayload {
  camera_id: string;
  classroom_id: string;
  timestamp: string;
}

export interface BuzzerPayload {
  alert_id: string;
  camera_id: string;
}

/** Alert lifecycle events push the full Alert row as their payload. */
export type AlertEventPayload = Alert;

export interface EventPayloadMap {
  ALERT_CREATED: AlertEventPayload;
  ALERT_ACKNOWLEDGED: AlertEventPayload;
  ALERT_RESOLVED: AlertEventPayload;
  BUZZER_TRIGGERED: BuzzerPayload;
  BUZZER_CLEARED: BuzzerPayload;
  CAMERA_OFFLINE: CameraLinkPayload;
  CAMERA_ONLINE: CameraLinkPayload;
  CLASSROOM_STATUS_CHANGED: ClassroomStatusChangedPayload;
  TRACKED_STATE_UPDATE: TrackedStateUpdatePayload;
}

export interface SocketEvent<T extends EventType = EventType> {
  type: T;
  payload: EventPayloadMap[T];
  timestamp: string;
}

export type SocketConnectionStatus = 'connecting' | 'open' | 'closed' | 'reconnecting';
