const CONFIG = {
  LOW: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  MEDIUM: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  HIGH: 'bg-red-500/15 text-red-400 border-red-500/30',
};

export function SeverityBadge({ severity }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${CONFIG[severity] ?? ''}`}
    >
      {severity}
    </span>
  );
}
