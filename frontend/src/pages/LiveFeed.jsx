import { useEffect, useState } from 'react';
import { Video, Clock } from 'lucide-react';
import Modal from '../components/Modal';
import { api } from '../services/api.js';
import { useDirectory } from '../hooks/useDirectory.js';
import { useLiveStatus } from '../hooks/useLiveStatus.js';
import { PrimaryButton } from '../components/Field';
import StatusPill from '../components/StatusPill';
import { alertStatusLabel, formatDuration, formatTime } from '../utils/format.js';

function Ring({ value, total }) {
  const r = 26;
  const c = 2 * Math.PI * r;
  const pct = total > 0 ? value / total : 0;
  return (
    <div className="ring-wrap">
      <svg viewBox="0 0 64 64">
        <circle cx="32" cy="32" r={r} fill="none" stroke="#eef0f5" strokeWidth="6" />
        <circle
          cx="32" cy="32" r={r} fill="none" stroke="#16a34a" strokeWidth="6" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - pct)} transform="rotate(-90 32 32)"
        />
      </svg>
      <div className="ring-num">{value}/{total}</div>
    </div>
  );
}

function CameraTile({ camera, classroomName, entry, onOpen }) {
  const unsupervised = entry?.supervision_status === 'UNSUPERVISED';
  return (
    <button className={`cam-card${unsupervised ? ' flagged' : ''}`} onClick={() => onOpen(camera)}>
      <div className="cam-thumb-lf">
        <img src={api.streamUrl(camera.id)} alt={camera.name} />
        <span className="live-badge"><span className="d" />Live</span>
        <span className="cam-id">{entry?.camera_status ?? 'UNKNOWN'}</span>
      </div>
      <div className="cam-card-body">
        <div className="cam-card-name">{camera.name}</div>
        <div className="cam-card-loc">{classroomName}</div>
      </div>
    </button>
  );
}

function DetailPanel({ camera, classroomName, entry, onClose }) {
  const [busy, setBusy] = useState(false);
  const [alert, setAlert] = useState(null);
  const alertId = entry?.active_alert_id;

  useEffect(() => {
    if (!alertId) { setAlert(null); return; }
    let cancelled = false;
    api.getAlert(alertId).then((a) => { if (!cancelled) setAlert(a); });
    return () => { cancelled = true; };
  }, [alertId]);

  async function handleAcknowledge() {
    if (!alertId) return;
    setBusy(true);
    try {
      const updated = await api.acknowledgeAlert(alertId);
      setAlert(updated);
    } finally {
      setBusy(false);
    }
  }

  const adultDetected = entry?.supervision_status === 'SUPERVISED' ? 'Yes' : 'No';
  const buzzerStatus = alert ? (alert.acknowledged_at ? 'Silenced' : 'Active') : null;

  if (!camera) return null;

  return (
    <Modal open onClose={onClose} title={camera.name} subtitle={classroomName} width={760}>
      <div className="cam-thumb" style={{ aspectRatio: '16 / 9' }}>
        <img src={api.streamUrl(camera.id)} alt={camera.name} />
        <span className="cam-badge" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#ef4444', display: 'inline-block' }} /> LIVE
        </span>
        <span className="cam-tag">{entry?.camera_status ?? 'UNKNOWN'}</span>
      </div>
      <ul className="sp-list">
        <li><span className="k">Camera status</span><span className="v">{entry?.camera_status ?? 'UNKNOWN'}</span></li>
        <li><span className="k">Adult detected</span><span className="v">{adultDetected}</span></li>
        <li><span className="k">Location</span><span className="v">{classroomName}</span></li>
      </ul>
      {alert && (
        <ul className="sp-list">
          <li><span className="k">Duration unattended</span><span className="v" style={{ display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'flex-end' }}><Clock size={12} />{formatDuration(alert.started_at, alert.resolved_at)}</span></li>
          <li><span className="k">Alert started</span><span className="v">{formatTime(alert.started_at)}</span></li>
          {alert.acknowledged_at && <li><span className="k">Acknowledged at</span><span className="v">{formatTime(alert.acknowledged_at)}</span></li>}
          <li><span className="k">Buzzer status</span><span className="v" style={{ color: buzzerStatus === 'Active' ? 'var(--red)' : 'var(--text-sub)' }}>{buzzerStatus}</span></li>
          <li><span className="k">Status</span><StatusPill status={alertStatusLabel(alert)} variant="alert" /></li>
        </ul>
      )}
      <PrimaryButton style={{ width: '100%', marginTop: 16, justifyContent: 'center' }} onClick={handleAcknowledge} disabled={busy || !alertId || !!alert?.acknowledged_at}>
        {!alertId ? 'No active alert' : alert?.acknowledged_at ? 'Acknowledged' : 'Acknowledge'}
      </PrimaryButton>
    </Modal>
  );
}

export default function LiveFeed() {
  const [showFlagged, setShowFlagged] = useState(false);
  const [selected, setSelected] = useState(null);
  const { cameras, classroomsById } = useDirectory();
  const { entries } = useLiveStatus();

  const total = cameras.length;
  const online = Array.from(entries.values()).filter((e) => e.camera_status === 'ONLINE').length;
  const unsupervisedCount = cameras.filter((c) => entries.get(c.id)?.supervision_status === 'UNSUPERVISED').length;
  const shown = showFlagged ? cameras.filter((c) => entries.get(c.id)?.supervision_status === 'UNSUPERVISED') : cameras;

  return (
    <>
      <div className="content-header">
        <div className="title-row"><div className="page-title">Live feed</div></div>
      </div>

      <div className="status-strip">
        <Ring value={online} total={total} />
        <div className="strip-block"><span className="strip-label">Total Cameras</span><span className="strip-value">{total}</span></div>
        <button className="strip-icon-btn"><Video /></button>
        <div className="strip-divider" />
        <div className="strip-block"><span className="strip-label">Unsupervised now</span><span className="strip-alert-num">{unsupervisedCount}</span></div>
        <div className="strip-divider" />
        <div><span className="status-dot green" /><span className="strip-mini-label">Online</span><span className="strip-mini-value">{online} cams</span></div>
        <div><span className="status-dot red" /><span className="strip-mini-label">Offline</span><span className="strip-mini-value">{total - online} cams</span></div>
      </div>

      <div className="pill-tab-row">
        <button className={`pill-tab${!showFlagged ? ' active' : ''}`} onClick={() => setShowFlagged(false)}>All cameras</button>
        {showFlagged && (
          <button className="pill-tab active" onClick={() => setShowFlagged(false)}>Unsupervised ✕</button>
        )}
      </div>

      <div className="lf-layout">
        <div className="analytics-panel">
          <div className="analytics-head"><div className="t">Analytics</div><div className="s">Click on analytics to view</div></div>
          <button className={`analytics-item${showFlagged ? ' active' : ''}`} onClick={() => setShowFlagged(true)}>
            <div><div className="name"><span className="yd" />Unsupervised</div></div>
            <span className="cnt">{unsupervisedCount}</span>
          </button>
        </div>

        <div className="cam-grid">
          {shown.map((cam) => (
            <CameraTile
              key={cam.id}
              camera={cam}
              classroomName={classroomsById.get(cam.classroom_id)?.name ?? cam.classroom_id}
              entry={entries.get(cam.id)}
              onOpen={setSelected}
            />
          ))}
        </div>
      </div>

      <DetailPanel
        camera={selected}
        classroomName={selected ? (classroomsById.get(selected.classroom_id)?.name ?? selected.classroom_id) : ''}
        entry={selected ? entries.get(selected.id) : null}
        onClose={() => setSelected(null)}
      />
    </>
  );
}
