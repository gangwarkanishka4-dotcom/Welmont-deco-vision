// Thin fetch-based REST client. Base URL comes from the single VITE_API_BASE env var
// (see .env) — the websocket URL is derived from this same value in hooks/useEventSocket.js.
export const API_BASE_URL = (import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8811').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request(path, init) {
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
  if (res.status === 204) return undefined;
  return res.json();
}

function qs(params = {}) {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== '');
  if (entries.length === 0) return '';
  return '?' + new URLSearchParams(entries).toString();
}

export const api = {
  health: () => request('/api/health'),

  // Classrooms
  listClassrooms: () => request('/api/classrooms'),
  createClassroom: (body) => request('/api/classrooms', { method: 'POST', body: JSON.stringify(body) }),
  getClassroomStatus: (id) => request(`/api/classrooms/${id}/status`),

  // Cameras
  listCameras: () => request('/api/cameras'),
  createCamera: (body) => request('/api/cameras', { method: 'POST', body: JSON.stringify(body) }),
  updateCamera: (id, body) => request(`/api/cameras/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteCamera: (id) => request(`/api/cameras/${id}`, { method: 'DELETE' }),
  enableCamera: (id) => request(`/api/cameras/${id}/enable`, { method: 'POST' }),
  disableCamera: (id) => request(`/api/cameras/${id}/disable`, { method: 'POST' }),
  testCamera: (id) => request(`/api/cameras/${id}/test`, { method: 'POST' }),
  streamUrl: (id) => `${API_BASE_URL}/api/cameras/${id}/stream`,
  getCameraConfiguration: (id) => request(`/api/cameras/${id}/configuration`),
  saveRoi: (id, body) => request(`/api/cameras/${id}/roi`, { method: 'POST', body: JSON.stringify(body) }),
  saveCalibration: (id, body) =>
    request(`/api/cameras/${id}/calibration`, { method: 'POST', body: JSON.stringify(body) }),
  saveGateLine: (id, body) => request(`/api/cameras/${id}/gate`, { method: 'POST', body: JSON.stringify(body) }),

  // Alerts
  // Alert.clip_url from the API is a path (e.g. /media/clips/<alert_id>.mp4)
  // served by the backend's StaticFiles mount — resolve it against the same
  // API origin the rest of this client talks to.
  clipUrl: (alert) => (alert?.clip_url ? `${API_BASE_URL}${alert.clip_url}` : null),
  listAlerts: (params = {}) => request(`/api/alerts${qs(params)}`),
  getAlert: (id) => request(`/api/alerts/${id}`),
  getAlertEvents: (id) => request(`/api/alerts/${id}/events`),
  acknowledgeAlert: (id) => request(`/api/alerts/${id}/acknowledge`, { method: 'POST' }),
  resolveAlert: (id) => request(`/api/alerts/${id}/resolve`, { method: 'POST' }),
};
