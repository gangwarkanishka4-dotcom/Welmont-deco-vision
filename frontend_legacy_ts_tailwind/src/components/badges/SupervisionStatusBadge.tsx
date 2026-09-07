import type { SupervisionStatus } from '../../types';

const CONFIG: Record<SupervisionStatus, { label: string; className: string; pulse?: boolean }> = {
  SUPERVISED: { label: 'Supervised', className: 'bg-status-supervised/15 text-status-supervised border-status-supervised/30' },
  WAITING_FOR_ADULT: { label: 'Waiting for Adult', className: 'bg-status-waiting/15 text-status-waiting border-status-waiting/30' },
  UNSUPERVISED: {
    label: 'Unsupervised',
    className: 'bg-status-unsupervised/15 text-status-unsupervised border-status-unsupervised/30',
    pulse: true,
  },
  EMPTY: { label: 'Empty', className: 'bg-status-empty/15 text-status-empty border-status-empty/30' },
  UNKNOWN: { label: 'Unknown', className: 'bg-slate-500/15 text-slate-400 border-slate-500/30' },
};

export function SupervisionStatusBadge({ status }: { status: SupervisionStatus }) {
  const cfg = CONFIG[status] ?? CONFIG.UNKNOWN;
  return (
    <span
      className={`relative inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${cfg.className}`}
    >
      {cfg.pulse && (
        <span className="absolute -left-0.5 -top-0.5 h-2 w-2 rounded-full bg-status-unsupervised animate-pulse-ring" />
      )}
      {cfg.label}
    </span>
  );
}
