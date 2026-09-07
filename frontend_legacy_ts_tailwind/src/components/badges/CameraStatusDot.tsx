import type { CameraLinkStatus, CameraStatus } from '../../types';

export function CameraStatusDot({ status }: { status: CameraLinkStatus | CameraStatus }) {
  const color =
    status === 'ONLINE' ? 'bg-status-supervised' : status === 'DISABLED' ? 'bg-slate-500' : 'bg-status-unsupervised';
  const label = status === 'ONLINE' ? 'Online' : status === 'DISABLED' ? 'Disabled' : 'Offline';
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-slate-400">
      <span className={`h-2 w-2 rounded-full ${color}`} />
      {label}
    </span>
  );
}
