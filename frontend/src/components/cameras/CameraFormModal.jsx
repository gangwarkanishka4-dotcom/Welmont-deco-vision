import { useState } from 'react';
import Modal from '../Modal.jsx';
import { Field, TextInput, Select, PrimaryButton, GhostButton } from '../Field.jsx';
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
    rtsp_password: '', // write-only — never pre-filled, only sent if the admin types a new one
    fps: String(camera.fps),
    resolution_width: String(camera.resolution_width),
    resolution_height: String(camera.resolution_height),
    enabled: camera.enabled,
  };
}

export default function CameraFormModal({ open, onClose, camera, onSaved }) {
  const { classrooms, refetchClassrooms } = useDirectory();
  const [form, setForm] = useState(() => (camera ? formFromCamera(camera) : emptyForm(classrooms)));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const [addingClassroom, setAddingClassroom] = useState(false);
  const [newClassroomName, setNewClassroomName] = useState('');
  const [newClassroomLocation, setNewClassroomLocation] = useState('');
  const [creatingClassroom, setCreatingClassroom] = useState(false);

  // Re-seed the form whenever a different camera is opened (or reopened for "add new").
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
      setError('Camera name, site, and RTSP host are required.');
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
    <Modal open={open} onClose={onClose} title={camera ? 'Edit camera' : 'Add camera'} subtitle="Connect RTSP feed to site" width={420}>
      <Field label="Camera name">
        <TextInput placeholder="eg. Basement Class 1" value={form.name} onChange={(e) => set('name', e.target.value)} />
      </Field>

      <Field label="Site">
        {!addingClassroom ? (
          <div className="flex gap-2">
            <Select value={form.classroom_id} onChange={(e) => set('classroom_id', e.target.value)}>
              {classrooms.length === 0 && <option value="">No sites yet</option>}
              {classrooms.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </Select>
            <GhostButton className="shrink-0" onClick={() => setAddingClassroom(true)}>+ New</GhostButton>
          </div>
        ) : (
          <div className="flex flex-col gap-2 rounded-lg border p-3" style={{ borderColor: 'var(--line)' }}>
            <TextInput placeholder="Site name" value={newClassroomName} onChange={(e) => setNewClassroomName(e.target.value)} />
            <TextInput placeholder="Location" value={newClassroomLocation} onChange={(e) => setNewClassroomLocation(e.target.value)} />
            <div className="flex gap-2">
              <PrimaryButton onClick={createClassroom} disabled={creatingClassroom}>Create</PrimaryButton>
              <GhostButton onClick={() => setAddingClassroom(false)}>Cancel</GhostButton>
            </div>
          </div>
        )}
      </Field>

      <Field label="RTSP host">
        <TextInput placeholder="192.168.1.50" value={form.rtsp_host} onChange={(e) => set('rtsp_host', e.target.value)} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="RTSP port">
          <TextInput value={form.rtsp_port} onChange={(e) => set('rtsp_port', e.target.value)} />
        </Field>
        <Field label="RTSP path">
          <TextInput placeholder="/stream1" value={form.rtsp_path} onChange={(e) => set('rtsp_path', e.target.value)} />
        </Field>
        <Field label="Username">
          <TextInput value={form.rtsp_username} onChange={(e) => set('rtsp_username', e.target.value)} />
        </Field>
        <Field label={camera ? 'Password (leave blank to keep current)' : 'Password'}>
          <TextInput type="password" autoComplete="new-password" value={form.rtsp_password} onChange={(e) => set('rtsp_password', e.target.value)} />
        </Field>
        <Field label="FPS">
          <TextInput value={form.fps} onChange={(e) => set('fps', e.target.value)} />
        </Field>
        <Field label="Enabled">
          <label className="flex items-center gap-2 text-sm h-[38px]">
            <input type="checkbox" checked={form.enabled} onChange={(e) => set('enabled', e.target.checked)} />
            Camera active
          </label>
        </Field>
        <Field label="Resolution width">
          <TextInput value={form.resolution_width} onChange={(e) => set('resolution_width', e.target.value)} />
        </Field>
        <Field label="Resolution height">
          <TextInput value={form.resolution_height} onChange={(e) => set('resolution_height', e.target.value)} />
        </Field>
      </div>

      {error && <p className="text-sm mb-3" style={{ color: 'var(--bad)' }}>{error}</p>}

      <div className="flex justify-end gap-2">
        <GhostButton onClick={onClose}>Cancel</GhostButton>
        <PrimaryButton onClick={submit} disabled={saving}>{camera ? 'Save changes' : 'Add'}</PrimaryButton>
      </div>
    </Modal>
  );
}
