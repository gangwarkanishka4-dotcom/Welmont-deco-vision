import { useNavigate } from 'react-router-dom';
import { SupervisionStatusBadge } from '../badges/SupervisionStatusBadge.jsx';
import { CameraStatusDot } from '../badges/CameraStatusDot.jsx';

export function CameraStatusCard({ entry }) {
  const navigate = useNavigate();
  const isUnsupervised = entry.supervision_status === 'UNSUPERVISED';

  return (
    <button
      onClick={() => navigate(`/live/${entry.camera_id}`)}
      className={`panel flex flex-col gap-3 p-4 text-left transition-colors hover:border-accent-500/60 ${
        isUnsupervised ? 'border-status-unsupervised/50' : ''
      }`}
    >
      {entry.active_alert_id && (
        <div className="-mx-4 -mt-4 mb-1 rounded-t-lg bg-status-unsupervised/90 px-4 py-1 text-xs font-semibold text-white">
          ACTIVE ALERT
        </div>
      )}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-semibold text-slate-100">{entry.classroom_name}</p>
          <p className="text-[11px] text-slate-500">Camera {entry.camera_id.slice(0, 8)}</p>
        </div>
        <CameraStatusDot status={entry.camera_status} />
      </div>

      <SupervisionStatusBadge status={entry.supervision_status} />

      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="rounded-md bg-surface-800 py-2">
          <p className="text-lg font-semibold text-slate-100">{entry.adult_count}</p>
          <p className="text-[10px] uppercase tracking-wide text-slate-500">Adults</p>
        </div>
        <div className="rounded-md bg-surface-800 py-2">
          <p className="text-lg font-semibold text-slate-100">{entry.child_count}</p>
          <p className="text-[10px] uppercase tracking-wide text-slate-500">Children</p>
        </div>
        <div className="rounded-md bg-surface-800 py-2">
          <p className="text-lg font-semibold text-slate-100">{entry.unknown_count}</p>
          <p className="text-[10px] uppercase tracking-wide text-slate-500">Unknown</p>
        </div>
      </div>
    </button>
  );
}
