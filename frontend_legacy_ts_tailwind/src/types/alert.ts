// Matches backend app/models/enums.py::AlertSeverity (no CRITICAL tier exists server-side).
export type AlertSeverity = 'LOW' | 'MEDIUM' | 'HIGH';
export type AlertStatus = 'ACTIVE' | 'ACKNOWLEDGED' | 'RESOLVED';

export interface Alert {
  alert_id: string;
  incident_id: string;
  camera_id: string;
  classroom_id: string;
  type: string;
  severity: AlertSeverity;
  status: AlertStatus;
  started_at: string;
  confirmed_at: string | null;
  resolved_at: string | null;
  children_count: number;
  adult_count: number;
  snapshot_url: string | null;
  clip_url: string | null;
}

export interface AlertEvent {
  id: string;
  alert_id: string;
  event_type: 'CREATED' | 'BUZZER_TRIGGERED' | 'ACKNOWLEDGED' | 'RESOLVED' | 'BUZZER_CLEARED' | string;
  message: string;
  created_at: string;
}

export interface AlertQueryParams {
  status?: AlertStatus;
  classroom_id?: string;
  limit?: number;
}
