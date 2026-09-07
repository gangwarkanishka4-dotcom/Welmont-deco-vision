import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useDirectory } from '../hooks/useDirectory';
import { useEventSocket } from '../hooks/useEventSocket';
import { api } from '../services/api';
import { EmptyState } from '../components/EmptyState';
import type { SupervisionStatus, TrackedStateUpdatePayload } from '../types';

const STATE_META: Record<SupervisionStatus, { icon: string; label: string; className: string }> = {
  SUPERVISED: { icon: '🟢', label: 'Supervised', className: 'text-status-supervised' },
  WAITING_FOR_ADULT: { icon: '🟠', label: 'Waiting for Adult', className: 'text-status-waiting' },
  UNSUPERVISED: { icon: '🔴', label: 'Unsupervised', className: 'text-status-unsupervised' },
  EMPTY: { icon: '⚪', label: 'Empty', className: 'text-slate-400' },
  UNKNOWN: { icon: '⚪', label: 'Unknown', className: 'text-slate-400' },
};

export function LiveMonitoringPage() {
  const { cameraId } = useParams<{ cameraId: string }>();
  const { camerasById, classroomsById, loading } = useDirectory();
  const [live, setLive] = useState<TrackedStateUpdatePayload | null>(null);
  const [debugOpen, setDebugOpen] = useState(false);

  useEventSocket(['TRACKED_STATE_UPDATE'], (evt) => {
    if (evt.payload.camera_id === cameraId) setLive(evt.payload);
  });

  if (loading) return <p className="text-sm text-slate-500">Loading camera…</p>;

  const camera = cameraId ? camerasById.get(cameraId) : undefined;
  if (!camera) {
    return (
      <EmptyState
        title="Camera not found"
        description="It may have been removed. Pick another camera from Live Monitoring."
        action={
          <Link to="/live" className="btn-secondary">
            Back to Live Monitoring
          </Link>
        }
      />
    );
  }

  const classroomName = classroomsById.get(camera.classroom_id)?.name ?? camera.classroom_id;
  const meta = STATE_META[live?.state ?? 'UNKNOWN'];

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <Link to="/live" className="text-xs text-slate-500 hover:text-slate-300">
            ← Live Monitoring
          </Link>
          <h2 className="text-base font-semibold text-slate-100">{classroomName}</h2>
          <p className="text-xs text-slate-500">{camera.name}</p>
        </div>
        <span className="flex items-center gap-1.5 text-xs font-bold text-status-unsupervised">
          <span className="h-1.5 w-1.5 animate-pulse-ring rounded-full bg-status-unsupervised" />
          LIVE
        </span>
      </div>

      <div className="flex flex-col gap-4 lg:flex-row">
        <div className="aspect-video flex-1 overflow-hidden rounded-md bg-black">
          {/* Bounding boxes/labels are burned in server-side; the browser renders the MJPEG
              multipart stream natively via <img>, no client-side overlay drawing needed. */}
          <img key={camera.id} src={api.streamUrl(camera.id)} alt={`${camera.name} live stream`} className="h-full w-full object-contain" />
        </div>

        <div className="flex w-full flex-col gap-3 lg:w-72">
          <div className="panel p-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Status</p>
            <p className={`text-lg font-bold ${meta.className}`}>
              {meta.icon} {meta.label}
            </p>
          </div>

          <div className="panel grid grid-cols-2 gap-3 p-4">
            <Stat label="Total Visible" value={live ? live.adult_count + live.child_count + live.unknown_count : '—'} />
            <Stat label="Adults" value={live?.adult_count ?? '—'} />
            <Stat label="Children" value={live?.child_count ?? '—'} />
            <Stat label="Unknown" value={live?.unknown_count ?? '—'} />
          </div>

          <button className="btn-ghost w-full justify-between" onClick={() => setDebugOpen((v) => !v)}>
            Debug Panel <span>{debugOpen ? '▲' : '▼'}</span>
          </button>
          {debugOpen && (
            <div className="panel space-y-1.5 p-4 text-xs text-slate-400">
              <Row label="FPS" value={live?.fps?.toFixed(1) ?? '—'} />
              <Row label="Inference" value={live ? `${live.inference_ms.toFixed(1)} ms` : '—'} />
              <Row label="Tracks" value={live?.people.length ?? '—'} />
              <Row label="Last Update" value={live ? new Date(live.timestamp).toLocaleTimeString() : '—'} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <p className="text-2xl font-bold text-slate-100">{value}</p>
      <p className="text-xs text-slate-500">{label}</p>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex justify-between">
      <span>{label}</span>
      <span className="font-mono text-slate-300">{value}</span>
    </div>
  );
}
