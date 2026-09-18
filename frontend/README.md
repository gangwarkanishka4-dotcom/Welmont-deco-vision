# DECO Vision — Welmont School Dashboard

Frontend build of the DECO Vision Figma design (Dashboard, Live Feed, Alerts/Incidents,
Site Management, Camera Management, User Management, Reports, Settings), wired up to the
real FastAPI backend in `../backend`.

## Run locally

```
npm install
cp .env.example .env   # then edit VITE_API_BASE if the backend isn't on 127.0.0.1:8811
npm run dev
```

Then open the printed localhost URL, with the backend already running (`../backend`).

## What's real vs. not yet

Dashboard, Live Feed (real video via the backend's MJPEG stream + live WebSocket
updates), Alerts, Incidents, Camera Management (including ROI/gate-line/height
calibration), and Site Management (mapped onto the backend's "classrooms," since there's
no multi-site concept yet) are all wired to the real backend — no mock data.

**User Management and Reports show an honest "not available yet" placeholder** — there's
no login/user-management system in the backend, and no report-generation endpoint.
`src/data/mockData.js` still exists only for `currentUser` (the Topbar avatar/name — no
real auth to source it from) and is otherwise unused.

## Stack

- React 19 + Vite
- react-router-dom for page routing
- Tailwind CSS v4 for styling
- lucide-react for icons

## Structure

- `src/components/` — Sidebar, Topbar, Modal, StatCard, StatusPill, TableCard, form fields
- `src/components/cameras/` — CameraFormModal (add/edit), CameraConfigModal (ROI/gate/calibration)
- `src/components/toast/` — AlertToastProvider (beep + spoken announcement on HIGH alerts)
- `src/pages/` — one file per screen
- `src/services/api.js` — REST client
- `src/websocket/` — shared WebSocket connection + React context
- `src/context/DirectoryProvider.jsx` — classroom/camera roster, fetched once
- `src/hooks/useLiveStatus.js` — live per-camera status (online/offline, supervision state, counts)
- `src/hooks/useAlertSound.js` — buzzer synthesis + text-to-speech announcements
- `src/data/mockData.js` — legacy Figma mock data (only `currentUser` still used)
