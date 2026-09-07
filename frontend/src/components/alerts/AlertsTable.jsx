import { useNavigate } from 'react-router-dom';
import { SeverityBadge } from '../badges/SeverityBadge.jsx';
import { AlertStatusBadge } from '../badges/AlertStatusBadge.jsx';

export function AlertsTable({ alerts, classroomsById }) {
  const navigate = useNavigate();

  return (
    <div className="panel overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-surface-700 text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="px-4 py-3">Snapshot</th>
            <th className="px-4 py-3">Classroom</th>
            <th className="px-4 py-3">Severity</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3">Children / Adults</th>
            <th className="px-4 py-3">Started</th>
            <th className="px-4 py-3">Confirmed</th>
            <th className="px-4 py-3">Resolved</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((a) => (
            <tr
              key={a.alert_id}
              className="cursor-pointer border-b border-surface-800 last:border-0 hover:bg-surface-800/60"
              onClick={() => navigate(`/alerts/${a.alert_id}`)}
            >
              <td className="px-4 py-2">
                {a.snapshot_url ? (
                  <img src={a.snapshot_url} alt="" className="h-10 w-16 rounded object-cover" />
                ) : (
                  <div className="h-10 w-16 rounded bg-surface-800" />
                )}
              </td>
              <td className="px-4 py-2 text-slate-200">{classroomsById.get(a.classroom_id)?.name ?? a.classroom_id}</td>
              <td className="px-4 py-2">
                <SeverityBadge severity={a.severity} />
              </td>
              <td className="px-4 py-2">
                <AlertStatusBadge status={a.status} />
              </td>
              <td className="px-4 py-2 text-slate-400">
                {a.children_count} / {a.adult_count}
              </td>
              <td className="px-4 py-2 text-slate-500">{new Date(a.started_at).toLocaleString()}</td>
              <td className="px-4 py-2 text-slate-500">{a.confirmed_at ? new Date(a.confirmed_at).toLocaleString() : '—'}</td>
              <td className="px-4 py-2 text-slate-500">{a.resolved_at ? new Date(a.resolved_at).toLocaleString() : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
