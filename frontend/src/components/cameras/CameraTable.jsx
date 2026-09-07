import { useState } from 'react';
import { api } from '../../services/api.js';
import { CameraStatusDot } from '../badges/CameraStatusDot.jsx';
import { Spinner } from '../Spinner.jsx';

export function CameraTable({ cameras, classroomsById, onEdit, onConfigure, onDeleted, onToggled }) {
  const [testState, setTestState] = useState({});
  const [busyId, setBusyId] = useState(null);

  async function handleTest(cam) {
    setTestState((s) => ({ ...s, [cam.id]: { testing: true } }));
    try {
      const res = await api.testCamera(cam.id);
      setTestState((s) => ({ ...s, [cam.id]: { testing: false, message: res.message, success: res.success } }));
    } catch (err) {
      setTestState((s) => ({
        ...s,
        [cam.id]: { testing: false, message: err instanceof Error ? err.message : 'Test failed', success: false },
      }));
    }
  }

  async function handleToggleEnabled(cam) {
    setBusyId(cam.id);
    try {
      if (cam.enabled) await api.disableCamera(cam.id);
      else await api.enableCamera(cam.id);
      onToggled();
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(cam) {
    if (!window.confirm(`Delete camera "${cam.name}"? This cannot be undone.`)) return;
    setBusyId(cam.id);
    try {
      await api.deleteCamera(cam.id);
      onDeleted();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="panel overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-surface-700 text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="px-4 py-3">Name</th>
            <th className="px-4 py-3">Classroom</th>
            <th className="px-4 py-3">RTSP Source</th>
            <th className="px-4 py-3">Resolution</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3">Enabled</th>
            <th className="px-4 py-3 text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {cameras.map((cam) => {
            const test = testState[cam.id];
            return (
              <tr key={cam.id} className="border-b border-surface-800 last:border-0">
                <td className="px-4 py-3 font-medium text-slate-100">{cam.name}</td>
                <td className="px-4 py-3 text-slate-400">{classroomsById.get(cam.classroom_id)?.name ?? '—'}</td>
                <td className="px-4 py-3 font-mono text-xs text-slate-500">
                  {cam.rtsp_host}:{cam.rtsp_port}
                  {cam.rtsp_path}
                </td>
                <td className="px-4 py-3 text-slate-400">
                  {cam.resolution_width}×{cam.resolution_height} @ {cam.fps}fps
                </td>
                <td className="px-4 py-3">
                  <CameraStatusDot status={cam.status} />
                </td>
                <td className="px-4 py-3">
                  <button
                    disabled={busyId === cam.id}
                    onClick={() => handleToggleEnabled(cam)}
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      cam.enabled ? 'bg-status-supervised/15 text-status-supervised' : 'bg-slate-600/20 text-slate-400'
                    }`}
                  >
                    {cam.enabled ? 'Enabled' : 'Disabled'}
                  </button>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-2 whitespace-nowrap">
                    {test?.message && (
                      <span className={`text-xs ${test.success ? 'text-status-supervised' : 'text-red-400'}`}>
                        {test.message}
                      </span>
                    )}
                    <button className="btn-secondary" onClick={() => handleTest(cam)} disabled={test?.testing}>
                      {test?.testing ? <Spinner /> : 'Test'}
                    </button>
                    <button className="btn-secondary" onClick={() => onConfigure(cam)}>
                      Configure
                    </button>
                    <button className="btn-secondary" onClick={() => onEdit(cam)}>
                      Edit
                    </button>
                    <button className="btn-danger" onClick={() => handleDelete(cam)} disabled={busyId === cam.id}>
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
