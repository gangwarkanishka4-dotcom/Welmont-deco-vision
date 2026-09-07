import { useState } from 'react';
import { Modal } from '../Modal.jsx';
import { Spinner } from '../Spinner.jsx';
import { api } from '../../services/api.js';
import { useDirectory } from '../../hooks/useDirectory.js';

function emptyForm(classrooms) {
  return {
    name: '',
    classroom_id: classrooms[0]?.id ?? '',
    rtsp_host: '',
    rtsp_port: '554',
    rtsp_path: '/stream1',
    rtsp_username: '',
    rtsp_password: '',
    fps: '10',
    resolution_width: '1920',
    resolution_height: '1080',
    enabled: true,
  };
}

function formFromCamera(camera) {
  return {
    name: camera.name,
    classroom_id: camera.classroom_id,
    rtsp_host: camera.rtsp_host,
    rtsp_port: String(camera.rtsp_port),
    rtsp_path: camera.rtsp_path,
    rtsp_username: camera.rtsp_username,
    rtsp_password: '', // write-only — never pre-filled, and only sent onward if the admin types a new one
    fps: String(camera.fps),
    resolution_width: String(camera.resolution_width),
    resolution_height: String(camera.resolution_height),
    enabled: camera.enabled,
  };
}

export function CameraFormModal({ open, onClose, camera, onSaved }) {
  const { classrooms, refetchClassrooms } = useDirectory();
  const [form, setForm] = useState(() => (camera ? formFromCamera(camera) : emptyForm(classrooms)));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const [addingClassroom, setAddingClassroom] = useState(false);
  const [newClassroomName, setNewClassroomName] = useState('');
  const [newClassroomLocation, setNewClassroomLocation] = useState('');
  const [creatingClassroom, setCreatingClassroom] = useState(false);

  // Re-seed the form whenever a different camera is opened (or the modal reopens for "add new").
  const [lastCameraId, setLastCameraId] = useState(undefined);
  if (open && camera?.id !== lastCameraId) {
    setLastCameraId(camera?.id ?? null);
    setForm(camera ? formFromCamera(camera) : emptyForm(classrooms));
    setError(null);
  }

  const set = (key, value) => setForm((f) => ({ ...f, [key]: value }));

  const createClassroom = async () => {
    if (!newClassroomName.trim()) return;
    setCreatingClassroom(true);
    try {
      const created = await api.createClassroom({ name: newClassroomName.trim(), location: newClassroomLocation.trim() });
      await refetchClassrooms();
      set('classroom_id', created.id);
      setAddingClassroom(false);
      setNewClassroomName('');
      setNewClassroomLocation('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create classroom');
    } finally {
      setCreatingClassroom(false);
    }
  };

  const submit = async () => {
    setError(null);
    if (!form.name.trim() || !form.classroom_id || !form.rtsp_host.trim()) {
      setError('Camera name, classroom, and RTSP host are required.');
      return;
    }
    setSaving(true);
    try {
      const base = {
        name: form.name.trim(),
        classroom_id: form.classroom_id,
        rtsp_host: form.rtsp_host.trim(),
        rtsp_port: Number(form.rtsp_port) || 554,
        rtsp_path: form.rtsp_path.trim(),
        rtsp_username: form.rtsp_username.trim(),
        fps: Number(form.fps) || 10,
        resolution_width: Number(form.resolution_width) || 1920,
        resolution_height: Number(form.resolution_height) || 1080,
        enabled: form.enabled,
      };
      if (camera) {
        const update = { ...base };
        if (form.rtsp_password) update.rtsp_password = form.rtsp_password;
        await api.updateCamera(camera.id, update);
      } else {
        await api.createCamera({ ...base, rtsp_password: form.rtsp_password });
      }
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save camera');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title={camera ? 'Edit Camera' : 'Add Camera'} widthClassName="max-w-2xl">
      <div className="grid grid-cols-2 gap-4">
        <div className="col-span-2">
          <label className="label">Camera Name</label>
          <input className="input w-full" value={form.name} onChange={(e) => set('name', e.target.value)} />
        </div>

        <div className="col-span-2">
          <label className="label">Classroom</label>
          {!addingClassroom ? (
            <div className="flex gap-2">
              <select
                className="input w-full"
                value={form.classroom_id}
                onChange={(e) => set('classroom_id', e.target.value)}
              >
                {classrooms.length === 0 && <option value="">No classrooms yet</option>}
                {classrooms.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
              <button className="btn-secondary shrink-0" onClick={() => setAddingClassroom(true)}>
                + New Classroom
              </button>
            </div>
          ) : (
            <div className="flex flex-col gap-2 rounded-md border border-surface-600 p-3">
              <input
                className="input w-full"
                placeholder="Classroom name"
                value={newClassroomName}
                onChange={(e) => setNewClassroomName(e.target.value)}
              />
              <input
                className="input w-full"
                placeholder="Location (e.g. Building A, Floor 2)"
                value={newClassroomLocation}
                onChange={(e) => setNewClassroomLocation(e.target.value)}
              />
              <div className="flex gap-2">
                <button className="btn-primary" disabled={creatingClassroom} onClick={createClassroom}>
                  {creatingClassroom ? <Spinner /> : 'Create'}
                </button>
                <button className="btn-ghost" onClick={() => setAddingClassroom(false)}>
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="col-span-2">
          <label className="label">RTSP Host</label>
          <input
            className="input w-full"
            value={form.rtsp_host}
            onChange={(e) => set('rtsp_host', e.target.value)}
            placeholder="192.168.1.50"
          />
        </div>
        <div>
          <label className="label">RTSP Port</label>
          <input className="input w-full" value={form.rtsp_port} onChange={(e) => set('rtsp_port', e.target.value)} />
        </div>
        <div>
          <label className="label">RTSP Path</label>
          <input
            className="input w-full"
            value={form.rtsp_path}
            onChange={(e) => set('rtsp_path', e.target.value)}
            placeholder="/stream1"
          />
        </div>
        <div>
          <label className="label">Username</label>
          <input
            className="input w-full"
            value={form.rtsp_username}
            onChange={(e) => set('rtsp_username', e.target.value)}
          />
        </div>
        <div>
          <label className="label">
            Password {camera && <span className="text-slate-600">(leave blank to keep current)</span>}
          </label>
          <input
            type="password"
            className="input w-full"
            value={form.rtsp_password}
            onChange={(e) => set('rtsp_password', e.target.value)}
            autoComplete="new-password"
          />
        </div>
        <div>
          <label className="label">FPS</label>
          <input className="input w-full" value={form.fps} onChange={(e) => set('fps', e.target.value)} />
        </div>
        <div className="flex items-end gap-2">
          <label className="flex items-center gap-2 pb-1.5 text-sm text-slate-300">
            <input type="checkbox" checked={form.enabled} onChange={(e) => set('enabled', e.target.checked)} />
            Enabled
          </label>
        </div>
        <div>
          <label className="label">Resolution Width</label>
          <input
            className="input w-full"
            value={form.resolution_width}
            onChange={(e) => set('resolution_width', e.target.value)}
          />
        </div>
        <div>
          <label className="label">Resolution Height</label>
          <input
            className="input w-full"
            value={form.resolution_height}
            onChange={(e) => set('resolution_height', e.target.value)}
          />
        </div>
      </div>

      {error && <p className="mt-3 text-sm text-status-unsupervised">{error}</p>}

      <div className="mt-5 flex justify-end gap-2">
        <button className="btn-secondary" onClick={onClose}>
          Cancel
        </button>
        <button className="btn-primary" disabled={saving} onClick={submit}>
          {saving ? <Spinner /> : camera ? 'Save Changes' : 'Add Camera'}
        </button>
      </div>
    </Modal>
  );
}
