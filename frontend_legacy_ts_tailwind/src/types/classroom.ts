export interface Classroom {
  id: string;
  name: string;
  location: string;
  created_at: string;
}

export type SupervisionStatus = 'EMPTY' | 'SUPERVISED' | 'WAITING_FOR_ADULT' | 'UNSUPERVISED' | 'UNKNOWN';

export type CameraLinkStatus = 'ONLINE' | 'OFFLINE';

export interface ClassroomStatusEntry {
  classroom_id: string;
  classroom_name: string;
  camera_id: string;
  camera_status: CameraLinkStatus;
  supervision_status: SupervisionStatus;
  adult_count: number;
  child_count: number;
  unknown_count: number;
  active_alert_id: string | null;
}
