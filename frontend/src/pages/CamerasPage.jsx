import { useState } from 'react';
import { useDirectory } from '../hooks/useDirectory.js';
import { EmptyState } from '../components/EmptyState.jsx';
import { CameraTable } from '../components/cameras/CameraTable.jsx';
import { CameraFormModal } from '../components/cameras/CameraFormModal.jsx';
import { CameraConfigModal } from '../components/cameras/CameraConfigModal.jsx';

export function CamerasPage() {
  const { cameras, classroomsById, loading, refetchCameras } = useDirectory();
  const [formOpen, setFormOpen] = useState(false);
  const [editingCamera, setEditingCamera] = useState(null);
  const [configuringCamera, setConfiguringCamera] = useState(null);

  const openAdd = () => {
    setEditingCamera(null);
    setFormOpen(true);
  };
  const openEdit = (camera) => {
    setEditingCamera(camera);
    setFormOpen(true);
  };

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-slate-400">Manage camera connections, ROI zones, and height calibration.</p>
        <button className="btn-primary" onClick={openAdd}>
          + Add Camera
        </button>
      </div>

      {loading ? (
        <p className="text-sm text-slate-500">Loading cameras…</p>
      ) : cameras.length === 0 ? (
        <EmptyState
          title="No cameras configured yet"
          description="Add your first camera to start supervising a classroom."
          action={
            <button className="btn-primary" onClick={openAdd}>
              + Add Camera
            </button>
          }
        />
      ) : (
        <CameraTable
          cameras={cameras}
          classroomsById={classroomsById}
          onEdit={openEdit}
          onConfigure={setConfiguringCamera}
          onDeleted={refetchCameras}
          onToggled={refetchCameras}
        />
      )}

      <CameraFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        camera={editingCamera}
        onSaved={() => {
          setFormOpen(false);
          refetchCameras();
        }}
      />

      {configuringCamera && (
        <CameraConfigModal open={true} onClose={() => setConfiguringCamera(null)} camera={configuringCamera} />
      )}
    </div>
  );
}
