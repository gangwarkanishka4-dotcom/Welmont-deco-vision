import { useEffect, useState } from 'react';
import { api } from '../services/api.js';
import { useDirectory } from '../hooks/useDirectory.js';
import { useEventSocket } from '../hooks/useEventSocket.js';
import { EmptyState } from '../components/EmptyState.jsx';
import { SupervisionStatusBadge } from '../components/badges/SupervisionStatusBadge.jsx';

// No dedicated /api/attendance endpoint exists on the backend yet — this view derives a
// present-headcount summary from the same per-classroom status the Dashboard uses.
export function AttendancePage() {
  const { classrooms, loading: directoryLoading } = useDirectory();
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (directoryLoading) return;
    let cancelled = false;
    (async () => {
      const results = await Promise.all(classrooms.map((c) => api.getClassroomStatus(c.id).catch(() => [])));
      if (!cancelled) {
        setEntries(results.flat());
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [classrooms, directoryLoading]);

  useEventSocket(['CLASSROOM_STATUS_CHANGED'], (evt) => {
    const p = evt.payload;
    setEntries((prev) => {
      const idx = prev.findIndex((e) => e.camera_id === p.camera_id);
      if (idx === -1) return prev;
      const next = [...prev];
      next[idx] = {
        ...next[idx],
        supervision_status: p.state,
        adult_count: p.adult_count,
        child_count: p.children_count,
        unknown_count: p.unknown_count,
      };
      return next;
    });
  });

  if (loading || directoryLoading) return <p className="text-sm text-slate-500">Loading attendance…</p>;

  if (entries.length === 0) {
    return <EmptyState title="No headcount data yet" description="Add classrooms and cameras to see live attendance." />;
  }

  const totals = entries.reduce(
    (acc, e) => ({
      adults: acc.adults + e.adult_count,
      children: acc.children + e.child_count,
      unknown: acc.unknown + e.unknown_count,
    }),
    { adults: 0, children: 0, unknown: 0 },
  );

  return (
    <div>
      <div className="mb-4 grid grid-cols-3 gap-4">
        <div className="panel p-4">
          <p className="text-2xl font-bold text-slate-100">{totals.adults}</p>
          <p className="text-xs text-slate-500">Adults Present</p>
        </div>
        <div className="panel p-4">
          <p className="text-2xl font-bold text-slate-100">{totals.children}</p>
          <p className="text-xs text-slate-500">Children Present</p>
        </div>
        <div className="panel p-4">
          <p className="text-2xl font-bold text-slate-100">{totals.unknown}</p>
          <p className="text-xs text-slate-500">Unclassified</p>
        </div>
      </div>

      <div className="panel overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-700 text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="px-4 py-3">Classroom</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Adults</th>
              <th className="px-4 py-3">Children</th>
              <th className="px-4 py-3">Unknown</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.camera_id} className="border-b border-surface-800 last:border-0">
                <td className="px-4 py-3 font-medium text-slate-100">{e.classroom_name}</td>
                <td className="px-4 py-3">
                  <SupervisionStatusBadge status={e.supervision_status} />
                </td>
                <td className="px-4 py-3 text-slate-300">{e.adult_count}</td>
                <td className="px-4 py-3 text-slate-300">{e.child_count}</td>
                <td className="px-4 py-3 text-slate-300">{e.unknown_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
