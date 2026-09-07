import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../services/api';
import { useEventSocket } from '../../hooks/useEventSocket';
import { useDirectory } from '../../hooks/useDirectory';
import { SeverityBadge } from '../badges/SeverityBadge';
import { AlertStatusBadge } from '../badges/AlertStatusBadge';
import type { Alert, AlertEvent } from '../../types';

export function AlertDetailView({ alertId }: { alertId: string }) {
  const [alert, setAlert] = useState<Alert | null>(null);
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const { classroomsById } = useDirectory();
  const navigate = useNavigate();

  useEffect(() => {
    setLoading(true);
    Promise.all([api.getAlert(alertId), api.getAlertEvents(alertId)])
      .then(([a, e]) => {
        setAlert(a);
        setEvents(e);
      })
      .finally(() => setLoading(false));
  }, [alertId]);

  // Other open tabs/views of this same alert should reflect ack/resolve actions taken elsewhere.
  useEventSocket(['ALERT_ACKNOWLEDGED', 'ALERT_RESOLVED'], (evt) => {
    if (evt.payload.alert_id === alertId) setAlert(evt.payload);
  });

  async function handleAcknowledge() {
    if (!alert) return;
    setBusy(true);
    try {
      const updated = await api.acknowledgeAlert(alert.alert_id);
      setAlert(updated);
      setEvents((prev) => [
        ...prev,
        { id: `local-ack-${Date.now()}`, alert_id: alert.alert_id, event_type: 'ACKNOWLEDGED', message: '', created_at: new Date().toISOString() },
      ]);
    } finally {
      setBusy(false);
    }
  }
  async function handleResolve() {
    if (!alert) return;
    setBusy(true);
    try {
      const updated = await api.resolveAlert(alert.alert_id);
      setAlert(updated);
      setEvents((prev) => [
        ...prev,
        { id: `local-res-${Date.now()}`, alert_id: alert.alert_id, event_type: 'RESOLVED', message: '', created_at: new Date().toISOString() },
      ]);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="text-sm text-slate-500">Loading incident…</p>;
  if (!alert) return <p className="text-sm text-slate-500">Alert not found.</p>;

  return (
    <div className="panel p-5">
      <div className="mb-4 flex items-start justify-between">
        <div>
          <button className="mb-2 text-xs text-accent-400 hover:underline" onClick={() => navigate('/alerts')}>
            ← Back to alerts
          </button>
          <h2 className="text-lg font-semibold text-slate-100">
            {classroomsById.get(alert.classroom_id)?.name ?? alert.classroom_id}
          </h2>
          <p className="text-xs text-slate-500">Incident {alert.incident_id}</p>
        </div>
        <div className="flex gap-2">
          <SeverityBadge severity={alert.severity} />
          <AlertStatusBadge status={alert.status} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
        <Field label="Children" value={String(alert.children_count)} />
        <Field label="Adults" value={String(alert.adult_count)} />
        <Field label="Started" value={new Date(alert.started_at).toLocaleString()} />
        <Field label="Resolved" value={alert.resolved_at ? new Date(alert.resolved_at).toLocaleString() : '—'} />
      </div>

      {alert.snapshot_url && (
        <img src={alert.snapshot_url} alt="Alert snapshot" className="mt-4 max-h-72 rounded-md border border-surface-700" />
      )}
      {alert.clip_url && (
        <a href={alert.clip_url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-sm text-accent-400 hover:underline">
          View clip →
        </a>
      )}

      <div className="mt-5 flex gap-2">
        <button className="btn-secondary" onClick={handleAcknowledge} disabled={busy || alert.status !== 'ACTIVE'}>
          Acknowledge
        </button>
        <button className="btn-danger" onClick={handleResolve} disabled={busy || alert.status === 'RESOLVED'}>
          Resolve
        </button>
      </div>

      <div className="mt-6">
        <h3 className="mb-2 text-sm font-semibold text-slate-300">Timeline</h3>
        <ul className="space-y-2 border-l border-surface-700 pl-4">
          {events.map((e) => (
            <li key={e.id} className="text-sm">
              <p className="text-slate-200">
                {e.event_type}
                {e.message ? ` — ${e.message}` : ''}
              </p>
              <p className="text-xs text-slate-500">{new Date(e.created_at).toLocaleString()}</p>
            </li>
          ))}
          {events.length === 0 && <li className="text-sm text-slate-500">No events recorded.</li>}
        </ul>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className="text-slate-200">{value}</p>
    </div>
  );
}
