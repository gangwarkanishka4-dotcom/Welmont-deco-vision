import { useCallback, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, X } from 'lucide-react';
import { useEventSocket } from '../../hooks/useEventSocket.js';
import { useDirectory } from '../../hooks/useDirectory.js';
import { useAnnounceOnce, useBeepOnce } from '../../hooks/useAlertSound.js';
import { PrimaryButton, GhostButton } from '../Field.jsx';

const AUTO_DISMISS_MS = 15_000;

export function AlertToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const { classroomsById } = useDirectory();
  const navigate = useNavigate();
  const beepOnce = useBeepOnce();
  const announceOnce = useAnnounceOnce();

  // Local-only by design: dismissing (X or the 15s auto-dismiss below) must
  // never call acknowledge/resolve — it only hides this transient popup.
  // The underlying alert stays ACTIVE until the real condition resolves
  // (adult returns) or someone resolves it from the Incidents page.
  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  useEventSocket(['ALERT_CREATED'], (evt) => {
    const alert = evt.payload;
    if (alert.severity !== 'HIGH') return;
    beepOnce(); // gated internally on the Settings sound toggle; fires exactly once per event
    const classroomName = classroomsById.get(alert.classroom_id)?.name ?? alert.classroom_id;
    announceOnce(`${classroomName} is unsupervised`);
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
                className="panel overflow-hidden rounded-xl border shadow-lg"
                style={{ borderColor: 'var(--bad)' }}
              >
                <div
                  className="flex items-center justify-between px-4 py-2"
                  style={{ background: 'var(--bad)' }}
                >
                  <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-white">
                    <AlertTriangle size={13} /> High Severity Alert
                  </span>
                  <button onClick={() => dismiss(t.id)} aria-label="Dismiss" className="text-white/80 hover:text-white">
                    <X size={14} />
                  </button>
                </div>
                <div className="px-4 py-3">
                  <p className="text-sm font-semibold">{classroomName}</p>
                  <p className="mt-0.5 text-sm" style={{ color: 'var(--bad)' }}>No supervising adult detected</p>
                  <p className="mt-1 text-xs" style={{ color: 'var(--ink-faint)' }}>
                    {t.alert.children_count} child{t.alert.children_count === 1 ? '' : 'ren'} present · started{' '}
                    {new Date(t.alert.started_at).toLocaleTimeString()}
                  </p>
                  <div className="mt-3 flex gap-2">
                    <PrimaryButton
                      className="flex-1"
                      onClick={() => {
                        navigate('/live-feed');
                        dismiss(t.id);
                      }}
                    >
                      View Live
                    </PrimaryButton>
                    <GhostButton
                      className="flex-1"
                      onClick={() => {
                        navigate('/alerts');
                        dismiss(t.id);
                      }}
                    >
                      View Alert
                    </GhostButton>
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
