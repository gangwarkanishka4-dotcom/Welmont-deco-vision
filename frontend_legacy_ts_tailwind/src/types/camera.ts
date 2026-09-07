export type CameraStatus = 'ONLINE' | 'OFFLINE' | 'DISABLED';

export interface Camera {
  id: string;
  name: string;
  classroom_id: string;
  rtsp_host: string;
  rtsp_port: number;
  rtsp_path: string;
  rtsp_username: string;
  fps: number;
  resolution_width: number;
  resolution_height: number;
  status: CameraStatus;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

/** Body for POST /api/cameras. Password is write-only and never echoed back by the API. */
export interface CameraCreateInput {
  name: string;
  classroom_id: string;
  rtsp_host: string;
  rtsp_port: number;
  rtsp_path: string;
  rtsp_username: string;
  rtsp_password: string;
  fps: number;
  resolution_width: number;
  resolution_height: number;
  enabled: boolean;
}

/** Body for PUT /api/cameras/{id}. Every field optional; omit rtsp_password to leave it unchanged. */
export type CameraUpdateInput = Partial<CameraCreateInput>;

export interface CameraTestResult {
  success: boolean;
  message: string;
}

export interface RoiPoint {
  x: number;
  y: number;
}

export interface CalibrationPoint {
  pixel_y: number;
  reference_height_px: number;
}

export interface CameraConfiguration {
  camera_id: string;
  roi: RoiPoint[];
  calibration_points: CalibrationPoint[];
  adult_height_ratio: number;
  child_height_ratio: number;
}

export interface RoiUpdateInput {
  roi: RoiPoint[];
}

export interface CalibrationUpdateInput {
  calibration_points: CalibrationPoint[];
  adult_height_ratio?: number;
  child_height_ratio?: number;
}
