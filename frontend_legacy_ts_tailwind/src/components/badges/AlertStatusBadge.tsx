import type { AlertStatus } from '../../types';

const CONFIG: Record<AlertStatus, string> = {
  ACTIVE: 'bg-red-500/15 text-red-400 border-red-500/30',
  ACKNOWLEDGED: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  RESOLVED: 'bg-status-supervised/15 text-status-supervised border-status-supervised/30',
};

export function AlertStatusBadge({ status }: { status: AlertStatus }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${CONFIG[status]}`}>
      {status}
    </span>
  );
}
