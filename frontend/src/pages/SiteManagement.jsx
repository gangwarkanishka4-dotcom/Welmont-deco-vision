import { useState } from 'react';
import { ChevronLeft, ChevronRight, Plus, Pencil, Trash2, X } from 'lucide-react';
import StatusPill from '../components/StatusPill';
import Modal from '../components/Modal';
import { Field, TextInput, PrimaryButton } from '../components/Field';
import { api } from '../services/api.js';
import { useDirectory } from '../hooks/useDirectory.js';
import { useLiveStatus } from '../hooks/useLiveStatus.js';

// Classroom create/delete/update: the backend only exposes list + create for
// classrooms today (no DELETE or PUT route) — Edit/Delete are shown disabled
// rather than silently doing nothing, same principle as the rest of this pass.
const NOT_SUPPORTED = 'Editing/removing a site isn’t supported by the backend yet';

export default function SiteManagement() {
  const { classrooms, cameras, refetchClassrooms } = useDirectory();
  const { entries } = useLiveStatus();
  const [addOpen, setAddOpen] = useState(false);
  const [popup, setPopup] = useState(null);
  const [form, setForm] = useState({ name: '', location: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const addSite = async () => {
    if (!form.name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await api.createClassroom({ name: form.name.trim(), location: form.location.trim() });
      await refetchClassrooms();
      setForm({ name: '', location: '' });
      setAddOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create site');
    } finally {
      setSaving(false);
    }
  };

  const rows = classrooms.map((c) => {
    const camsHere = cameras.filter((cam) => cam.classroom_id === c.id);
    const activeHere = camsHere.filter((cam) => entries.get(cam.id)?.camera_status === 'ONLINE').length;
    const status = camsHere.length === 0 ? 'Inactive' : activeHere === camsHere.length ? 'Active' : 'Partial';
    return { ...c, camerasHere: camsHere, activeHere, status };
  });

  return (
    <>
      <div className="content-header">
        <div className="title-row"><div className="page-title">Site Management</div></div>
        <PrimaryButton onClick={() => setAddOpen(true)}><Plus size={15} /> Add Site</PrimaryButton>
      </div>

      <div style={{ position: 'relative' }}>
        <div className="table-wrap">
          <table className="col-fixed">
            <colgroup>
              <col style={{ width: '26%' }} />
              <col style={{ width: '22%' }} />
              <col style={{ width: '13%' }} />
              <col style={{ width: '13%' }} />
              <col style={{ width: '14%' }} />
              <col style={{ width: '12%' }} />
            </colgroup>
            <thead><tr><th>Site</th><th>Location</th><th className="num">Cameras</th><th className="num">Active</th><th className="center">Status</th><th>Actions</th></tr></thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id} className="clickable" onClick={() => setPopup(s)}>
                  <td className="loc">{s.name}</td>
                  <td>{s.location || '—'}</td>
                  <td className="num tabular">{s.camerasHere.length}</td>
                  <td className="num tabular">{s.activeHere}</td>
                  <td className="center"><StatusPill status={s.status} /></td>
                  <td className="actions-cell" onClick={(e) => e.stopPropagation()}>
                    <button className="kebab" disabled title={NOT_SUPPORTED} style={{ opacity: 0.4, cursor: 'not-allowed' }}><Pencil size={14} /></button>
                    <button className="trash-btn" disabled title={NOT_SUPPORTED} style={{ opacity: 0.4, cursor: 'not-allowed' }}><Trash2 /></button>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-sub)', padding: 32 }}>No sites yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {popup && (
          <div className="site-detail-panel open">
            <div className="sdp-head">
              Site cameras
              <button className="sdp-close" onClick={() => setPopup(null)}><X size={12} /></button>
            </div>
            <div className="sdp-crumb"><ChevronLeft size={12} /><span>{popup.location || popup.name}</span><ChevronRight size={12} /></div>
            <div>
              {popup.camerasHere.map((cam) => (
                <div key={cam.id} className="sdp-row">
                  <span>{cam.name}</span>
                  <StatusPill status={entries.get(cam.id)?.camera_status ?? 'UNKNOWN'} />
                </div>
              ))}
              {popup.camerasHere.length === 0 && (
                <div className="sdp-row" style={{ color: 'var(--text-sub)' }}>No cameras assigned to this site.</div>
              )}
            </div>
            <div className="sdp-foot">
              <div>Total Cameras<div style={{ fontWeight: 700, fontSize: 15, marginTop: 2 }}>{popup.camerasHere.length}</div></div>
              <div>Offline<div style={{ fontWeight: 700, fontSize: 15, marginTop: 2 }}>{popup.camerasHere.length - popup.activeHere}</div></div>
            </div>
          </div>
        )}
      </div>

      <Modal open={addOpen} onClose={() => setAddOpen(false)} title="Add Site" subtitle="Connect a school to your dashboard" width={380}>
        <Field label="Site name">
          <TextInput placeholder="eg. Welmont Lalkothi" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        <Field label="Location">
          <TextInput placeholder="eg. Jaipur" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
        </Field>
        {error && <p style={{ fontSize: 13, color: 'var(--red)', marginBottom: 12 }}>{error}</p>}
        <div className="modal-actions">
          <button className="btn-cancel" onClick={() => setAddOpen(false)}>Cancel</button>
          <button className="btn-confirm" onClick={addSite} disabled={saving}>Add</button>
        </div>
      </Modal>
    </>
  );
}
