import { useCallback, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { useEventSocket } from '../../hooks/useEventSocket.js';
import { useDirectory } from '../../hooks/useDirectory.js';
import { useBeepOnce } from '../../hooks/useAlertSound.js';

const AUTO_DISMISS_MS = 15_000;

export function AlertToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const { classroomsById } = useDirectory();
  const navigate = useNavigate();
  const beepOnce = useBeepOnce();

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  useEventSocket(['ALERT_CREATED'], (evt) => {
    const alert = evt.payload;
    if (alert.severity !== 'HIGH') return;
    beepOnce(); // gated internally on the Settings sound toggle; fires exactly once per event
    const id = `${alert.alert_id}-${evt.timestamp}`;
    setToasts((prev) => [...prev, { id, alert, createdAt: Date.now() }]);
    setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
  });

  return (
    <>
      {children}
      {createPortal(
        <div className="fixed right-4 top-4 z-[100] flex w-96 flex-col gap-3">
          {toasts.map((t) => {
            const classroomName = classroomsById.get(t.alert.classroom_id)?.name ?? t.alert.classroom_id;
            return (
              <div
                key={t.id}
                className="animate-slide-in overflow-hidden rounded-lg border border-red-500/40 bg-surface-850 shadow-lg"
              >
                <div className="flex items-center justify-between bg-red-600/90 px-4 py-1.5">
                  <span className="text-xs font-bold uppercase tracking-wide text-white">High Severity Alert</span>
                  <button onClick={() => dismiss(t.id)} className="text-white/80 hover:text-white" aria-label="Dismiss">
                    ✕
                  </button>
                </div>
                <div className="px-4 py-3">
                  <p className="text-sm font-semibold text-slate-100">{classroomName}</p>
                  <p className="mt-0.5 text-sm text-red-300">No supervising adult detected</p>
                  <p className="mt-1 text-xs text-slate-400">
                    {t.alert.children_count} child{t.alert.children_count === 1 ? '' : 'ren'} present · started{' '}
                    {new Date(t.alert.started_at).toLocaleTimeString()}
                  </p>
                  <div className="mt-3 flex gap-2">
                    <button
                      className="btn-primary flex-1"
                      onClick={() => {
                        navigate(`/live/${t.alert.camera_id}`);
                        dismiss(t.id);
                      }}
                    >
                      View Live
                    </button>
                    <button
                      className="btn-secondary flex-1"
                      onClick={() => {
                        navigate(`/alerts/${t.alert.alert_id}`);
                        dismiss(t.id);
                      }}
                    >
                      View Incident
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>,
        document.body,
      )}
    </>
  );
}
