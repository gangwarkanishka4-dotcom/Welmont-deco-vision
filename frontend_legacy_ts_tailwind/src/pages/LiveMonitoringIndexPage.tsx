import { Link } from 'react-router-dom';
import { useDirectory } from '../hooks/useDirectory';
import { CameraStatusDot } from '../components/badges/CameraStatusDot';
import { EmptyState } from '../components/EmptyState';

export function LiveMonitoringIndexPage() {
  const { cameras, classroomsById, loading } = useDirectory();

  if (loading) return <p className="text-sm text-slate-500">Loading cameras…</p>;

  if (cameras.length === 0) {
    return (
      <EmptyState
        title="No cameras configured yet"
        description="Add a camera from the Cameras page to start live monitoring."
      />
    );
  }

  return (
    <div>
      <p className="mb-4 text-sm text-slate-400">Select a camera to open its live feed.</p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {cameras.map((cam) => (
          <Link
            key={cam.id}
            to={`/live/${cam.id}`}
            className="panel flex flex-col gap-2 p-4 transition-colors hover:border-accent-500/60"
          >
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-slate-100">{cam.name}</p>
              <CameraStatusDot status={cam.status} />
            </div>
            <p className="text-xs text-slate-500">{classroomsById.get(cam.classroom_id)?.name ?? cam.classroom_id}</p>
            <p className="text-xs text-slate-600">
              {cam.resolution_width}×{cam.resolution_height} @ {cam.fps}fps
            </p>
          </Link>
        ))}
      </div>
    </div>
  );
}
