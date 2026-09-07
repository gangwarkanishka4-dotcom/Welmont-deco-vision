import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../services/api.js';
import { useDirectory } from '../hooks/useDirectory.js';
import { useEventSocket } from '../hooks/useEventSocket.js';
import { EmptyState } from '../components/EmptyState.jsx';
import { AlertsTable } from '../components/alerts/AlertsTable.jsx';
import { AlertDetailView } from '../components/alerts/AlertDetailView.jsx';

function AlertsListView() {
  const { classrooms, classroomsById } = useDirectory();
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState('');
  const [classroomId, setClassroomId] = useState('');

  // loading is flipped back on from the select onChange handlers below (the event that causes
  // the refetch), so this effect only needs to turn it off once the new page of alerts lands.
  useEffect(() => {
    api
      .listAlerts({ status: status || undefined, classroom_id: classroomId || undefined, limit: 200 })
      .then(setAlerts)
      .finally(() => setLoading(false));
  }, [status, classroomId]);

  // Reflect lifecycle changes from any open view (toast, incident detail, another tab) live.
  useEventSocket(['ALERT_CREATED', 'ALERT_ACKNOWLEDGED', 'ALERT_RESOLVED'], (evt) => {
    const alert = evt.payload;
    setAlerts((prev) => {
      if (status && alert.status !== status) return prev.filter((a) => a.alert_id !== alert.alert_id);
      if (classroomId && alert.classroom_id !== classroomId) return prev;
      const exists = prev.some((a) => a.alert_id === alert.alert_id);
      if (exists) return prev.map((a) => (a.alert_id === alert.alert_id ? alert : a));
      return [alert, ...prev];
    });
  });

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-3">
        <select
          className="input"
          value={status}
          onChange={(e) => {
            setLoading(true);
            setStatus(e.target.value);
          }}
        >
          <option value="">All statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="ACKNOWLEDGED">Acknowledged</option>
          <option value="RESOLVED">Resolved</option>
        </select>
        <select
          className="input"
          value={classroomId}
          onChange={(e) => {
            setLoading(true);
            setClassroomId(e.target.value);
          }}
        >
          <option value="">All classrooms</option>
          {classrooms.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>

      {loading ? (
        <p className="text-sm text-slate-500">Loading alerts…</p>
      ) : alerts.length === 0 ? (
        <EmptyState title="No alerts found" description="Nothing matches the current filters, or none have fired yet." />
      ) : (
        <AlertsTable alerts={alerts} classroomsById={classroomsById} />
      )}
    </div>
  );
}

export function AlertsPage() {
  const { alertId } = useParams();
  // key={alertId} forces a full remount on navigation between incidents, so AlertDetailView's
  // loading state starts fresh from its useState initializer instead of needing an effect reset.
  return alertId ? <AlertDetailView key={alertId} alertId={alertId} /> : <AlertsListView />;
}
