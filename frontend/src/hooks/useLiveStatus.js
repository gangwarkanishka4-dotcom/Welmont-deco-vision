import { useEffect, useState } from 'react';
import { api } from '../services/api.js';
import { useDirectory } from './useDirectory.js';
import { useEventSocket } from './useEventSocket.js';

/**
 * One entry per camera, keyed by camera_id — mirrors app.schemas.alert.ClassroomStatusOut:
 * { classroom_id, classroom_name, camera_id, camera_status, supervision_status,
 *   adult_count, child_count, unknown_count, active_alert_id }
 *
 * Fetched once per classroom on mount (roster + initial status, no polling), then kept live
 * over the websocket, so every page needing "is this camera online / supervised / how many
 * people" can share one fetch+subscribe path instead of re-implementing it per page.
 */
export function useLiveStatus() {
  const { classrooms, loading: directoryLoading } = useDirectory();
  const [entries, setEntries] = useState(new Map());
  const [loading, setLoading] = useState(true);

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

  return { entries, loading: loading || directoryLoading };
}

/** Live per-track counts/boxes for one camera's video, straight off the
 * TRACKED_STATE_UPDATE stream — the same payload the burned-in video overlay
 * is rendered from server-side, used here for the text/stat side of a
 * detail panel rather than drawing anything client-side. */
export function useCameraLiveState(cameraId) {
  const [live, setLive] = useState(null);
  useEventSocket(['TRACKED_STATE_UPDATE'], (evt) => {
    if (evt.payload.camera_id === cameraId) setLive(evt.payload);
  });
  return live;
}
