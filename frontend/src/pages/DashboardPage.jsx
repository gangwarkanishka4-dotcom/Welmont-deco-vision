import { useEffect, useState } from 'react';
import { api } from '../services/api.js';
import { useDirectory } from '../hooks/useDirectory.js';
import { useEventSocket } from '../hooks/useEventSocket.js';
import { CameraStatusCard } from '../components/dashboard/CameraStatusCard.jsx';
import { EmptyState } from '../components/EmptyState.jsx';

export function DashboardPage() {
  const { classrooms, loading: directoryLoading } = useDirectory();
  const [entries, setEntries] = useState(new Map());
  const [loading, setLoading] = useState(true);

  // Roster + initial status fetched once on mount per the spec — all subsequent updates are
  // pushed over the websocket rather than polled.
  useEffect(() => {
    if (directoryLoading) return;
    let cancelled = false;
    (async () => {
      const results = await Promise.all(classrooms.map((c) => api.getClassroomStatus(c.id).catch(() => [])));
      if (cancelled) return;
      const next = new Map();
      results.flat().forEach((entry) => next.set(entry.camera_id, entry));
      setEntries(next);
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [classrooms, directoryLoading]);

  useEventSocket(['CLASSROOM_STATUS_CHANGED'], (evt) => {
    const p = evt.payload;
    setEntries((prev) => {
      const next = new Map(prev);
      const existing = next.get(p.camera_id);
      next.set(p.camera_id, {
        classroom_id: p.classroom_id,
        classroom_name: existing?.classroom_name ?? p.classroom_id,
        camera_id: p.camera_id,
        camera_status: existing?.camera_status ?? 'ONLINE',
        supervision_status: p.state,
        adult_count: p.adult_count,
        child_count: p.children_count,
        unknown_count: p.unknown_count,
        active_alert_id: existing?.active_alert_id ?? null,
      });
      return next;
    });
  });

  useEventSocket(['CAMERA_OFFLINE', 'CAMERA_ONLINE'], (evt) => {
    const p = evt.payload;
    const status = evt.type === 'CAMERA_ONLINE' ? 'ONLINE' : 'OFFLINE';
    setEntries((prev) => {
      const existing = prev.get(p.camera_id);
      if (!existing) return prev;
      const next = new Map(prev);
      next.set(p.camera_id, { ...existing, camera_status: status });
      return next;
    });
  });

  // Keep the "active alert" ribbon live without waiting for the next CLASSROOM_STATUS_CHANGED tick.
  useEventSocket(['ALERT_CREATED'], (evt) => {
    const alert = evt.payload;
    setEntries((prev) => {
      const existing = prev.get(alert.camera_id);
      if (!existing) return prev;
      const next = new Map(prev);
      next.set(alert.camera_id, { ...existing, active_alert_id: alert.alert_id });
      return next;
    });
  });
  useEventSocket(['ALERT_RESOLVED'], (evt) => {
    const alert = evt.payload;
    setEntries((prev) => {
      const existing = prev.get(alert.camera_id);
      if (!existing || existing.active_alert_id !== alert.alert_id) return prev;
      const next = new Map(prev);
      next.set(alert.camera_id, { ...existing, active_alert_id: null });
      return next;
    });
  });

  if (loading || directoryLoading) {
    return <p className="text-sm text-slate-500">Loading classroom status…</p>;
  }

  if (classrooms.length === 0) {
    return (
      <EmptyState
        title="No classrooms configured yet"
        description="Add a classroom and a camera from the Cameras page to start monitoring."
      />
    );
  }

  const cards = Array.from(entries.values());

  if (cards.length === 0) {
    return (
      <EmptyState
        title="No cameras configured yet"
        description="Classrooms exist but none have a camera assigned. Add one from the Cameras page."
      />
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {cards.map((entry) => (
        <CameraStatusCard key={entry.camera_id} entry={entry} />
      ))}
    </div>
  );
}
