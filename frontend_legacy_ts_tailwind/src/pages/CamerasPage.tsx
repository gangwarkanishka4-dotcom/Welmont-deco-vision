import { useState } from 'react';
import { useDirectory } from '../hooks/useDirectory';
import { EmptyState } from '../components/EmptyState';
import { CameraTable } from '../components/cameras/CameraTable';
import { CameraFormModal } from '../components/cameras/CameraFormModal';
import { CameraConfigModal } from '../components/cameras/CameraConfigModal';
import type { Camera } from '../types';

export function CamerasPage() {
  const { cameras, classroomsById, loading, refetchCameras } = useDirectory();
  const [formOpen, setFormOpen] = useState(false);
  const [editingCamera, setEditingCamera] = useState<Camera | null>(null);
  const [configuringCamera, setConfiguringCamera] = useState<Camera | null>(null);

  const openAdd = () => {
    setEditingCamera(null);
    setFormOpen(true);
  };
  const openEdit = (camera: Camera) => {
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
