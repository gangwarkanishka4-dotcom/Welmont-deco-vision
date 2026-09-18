import { useState } from 'react';
import { Plus, Pencil, Trash2, Video, VideoOff, Bookmark } from 'lucide-react';
import KpiCard from '../components/KpiCard';
import StatusPill from '../components/StatusPill';
import { PrimaryButton, GhostButton } from '../components/Field';
import CameraFormModal from '../components/cameras/CameraFormModal.jsx';
import CameraConfigModal from '../components/cameras/CameraConfigModal.jsx';
import { api } from '../services/api.js';
import { useDirectory } from '../hooks/useDirectory.js';
import { useLiveStatus } from '../hooks/useLiveStatus.js';
import { maskRtspUrl } from '../utils/format.js';

export default function CameraManagement() {
  const { cameras, classroomsById, refetchCameras } = useDirectory();
  const { entries } = useLiveStatus();
  const [formOpen, setFormOpen] = useState(false);
  const [editingCamera, setEditingCamera] = useState(null);
  const [configuringCamera, setConfiguringCamera] = useState(null);
  const [testState, setTestState] = useState({});
  const [busyId, setBusyId] = useState(null);

  const onlineCount = cameras.filter((c) => entries.get(c.id)?.camera_status === 'ONLINE').length;
  const offlineCount = cameras.length - onlineCount;

  async function handleTest(cam) {
    setTestState((s) => ({ ...s, [cam.id]: { testing: true } }));
    try {
      const res = await api.testCamera(cam.id);
      setTestState((s) => ({ ...s, [cam.id]: { testing: false, message: res.message, success: res.success } }));
    } catch (err) {
      setTestState((s) => ({ ...s, [cam.id]: { testing: false, message: err instanceof Error ? err.message : 'Test failed', success: false } }));
    }
  }

  async function handleToggleEnabled(cam) {
    setBusyId(cam.id);
    try {
      if (cam.enabled) await api.disableCamera(cam.id);
      else await api.enableCamera(cam.id);
      await refetchCameras();
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(cam) {
    if (!window.confirm(`Delete camera "${cam.name}"? This cannot be undone.`)) return;
    setBusyId(cam.id);
    try {
      await api.deleteCamera(cam.id);
      await refetchCameras();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <div className="content-header">
        <div className="title-row"><div className="page-title">Camera Management</div><button className="bookmark-btn"><Bookmark size={15} /></button></div>
        <PrimaryButton onClick={() => { setEditingCamera(null); setFormOpen(true); }}><Plus size={15} /> Add camera</PrimaryButton>
      </div>

      <div className="kpi-grid">
        <KpiCard accent="blue" icon={Video} number={cameras.length} label="Total Cameras" />
        <KpiCard accent="green" icon={Video} number={onlineCount} label="Cameras Online" />
        <KpiCard accent="red" icon={VideoOff} number={offlineCount} label="Cameras Offline" />
      </div>

      <div className="table-wrap">
        <table className="col-fixed">
          <colgroup>
            <col style={{ width: '17%' }} />
            <col style={{ width: '15%' }} />
            <col style={{ width: '19%' }} />
            <col style={{ width: '10%' }} />
            <col style={{ width: '10%' }} />
            <col style={{ width: '29%' }} />
          </colgroup>
          <thead><tr><th>Name</th><th>Site</th><th>RTSP</th><th className="center">Status</th><th className="center">Enabled</th><th>Actions</th></tr></thead>
          <tbody>
            {cameras.map((c) => {
              const test = testState[c.id];
              return (
                <tr key={c.id}>
                  <td className="loc">{c.name}</td>
                  <td>{classroomsById.get(c.classroom_id)?.name ?? '—'}</td>
                  <td className="rtsp-cell">{maskRtspUrl(c.rtsp_host, c.rtsp_port, c.rtsp_path)}</td>
                  <td className="center"><StatusPill status={entries.get(c.id)?.camera_status ?? 'UNKNOWN'} /></td>
                  <td className="center">
                    <button
                      disabled={busyId === c.id}
                      onClick={() => handleToggleEnabled(c)}
                      className={`pill ${c.enabled ? 'green' : 'gray'}`}
                      style={{ border: 'none', cursor: 'pointer' }}
                    >
                      {c.enabled ? 'Enabled' : 'Disabled'}
                    </button>
                  </td>
                  <td className="actions-cell">
                    {test?.message && (
                      <span style={{ fontSize: 11.5, color: test.success ? 'var(--green-text)' : 'var(--red)', marginRight: 4 }}>{test.message}</span>
                    )}
                    <GhostButton style={{ padding: '6px 10px', fontSize: 12.5 }} onClick={() => handleTest(c)} disabled={test?.testing}>Test</GhostButton>
                    <GhostButton style={{ padding: '6px 10px', fontSize: 12.5 }} onClick={() => setConfiguringCamera(c)}>Configure</GhostButton>
                    <button className="kebab" onClick={() => { setEditingCamera(c); setFormOpen(true); }}><Pencil size={14} /></button>
                    <button className="trash-btn" onClick={() => handleDelete(c)} disabled={busyId === c.id}><Trash2 /></button>
                  </td>
                </tr>
              );
            })}
            {cameras.length === 0 && (
              <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-sub)', padding: 32 }}>No cameras yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <CameraFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        camera={editingCamera}
        onSaved={() => { setFormOpen(false); refetchCameras(); }}
      />

      {configuringCamera && (
        <CameraConfigModal open camera={configuringCamera} onClose={() => setConfiguringCamera(null)} />
      )}
    </>
  );
}
