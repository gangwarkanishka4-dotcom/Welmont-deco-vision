import type {
  Alert,
  AlertEvent,
  AlertStatus,
  Camera,
  CameraCreateInput,
  CameraUpdateInput,
  CameraTestResult,
  CameraConfiguration,
  RoiUpdateInput,
  CalibrationUpdateInput,
  Classroom,
  ClassroomStatusEntry,
} from '../types';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function qs(params: Record<string, string | number | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== '');
  if (entries.length === 0) return '';
  return '?' + new URLSearchParams(entries as [string, string][]).toString();
}

export const api = {
  health: () => request<{ status: string }>('/api/health'),

  // Classrooms
  listClassrooms: () => request<Classroom[]>('/api/classrooms'),
  createClassroom: (body: { name: string; location: string }) =>
    request<Classroom>('/api/classrooms', { method: 'POST', body: JSON.stringify(body) }),
  getClassroomStatus: (id: string) =>
    request<ClassroomStatusEntry[]>(`/api/classrooms/${id}/status`),

  // Cameras
  listCameras: () => request<Camera[]>('/api/cameras'),
  createCamera: (body: CameraCreateInput) =>
    request<Camera>('/api/cameras', { method: 'POST', body: JSON.stringify(body) }),
  updateCamera: (id: string, body: CameraUpdateInput) =>
    request<Camera>(`/api/cameras/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteCamera: (id: string) => request<void>(`/api/cameras/${id}`, { method: 'DELETE' }),
  enableCamera: (id: string) => request<Camera>(`/api/cameras/${id}/enable`, { method: 'POST' }),
  disableCamera: (id: string) => request<Camera>(`/api/cameras/${id}/disable`, { method: 'POST' }),
  testCamera: (id: string) => request<CameraTestResult>(`/api/cameras/${id}/test`, { method: 'POST' }),
  streamUrl: (id: string) => `${API_BASE_URL}/api/cameras/${id}/stream`,
  getCameraConfiguration: (id: string) =>
    request<CameraConfiguration>(`/api/cameras/${id}/configuration`),
  saveRoi: (id: string, body: RoiUpdateInput) =>
    request<CameraConfiguration>(`/api/cameras/${id}/roi`, { method: 'POST', body: JSON.stringify(body) }),
  saveCalibration: (id: string, body: CalibrationUpdateInput) =>
    request<CameraConfiguration>(`/api/cameras/${id}/calibration`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  // Alerts
  listAlerts: (params: { status?: AlertStatus; classroom_id?: string; limit?: number } = {}) =>
    request<Alert[]>(`/api/alerts${qs(params)}`),
  getAlert: (id: string) => request<Alert>(`/api/alerts/${id}`),
  getAlertEvents: (id: string) => request<AlertEvent[]>(`/api/alerts/${id}/events`),
  acknowledgeAlert: (id: string) => request<Alert>(`/api/alerts/${id}/acknowledge`, { method: 'POST' }),
  resolveAlert: (id: string) => request<Alert>(`/api/alerts/${id}/resolve`, { method: 'POST' }),
};

export { ApiError };
