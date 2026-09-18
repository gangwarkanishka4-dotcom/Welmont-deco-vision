// Two pill families exist in the design: `.status-pill.*` (alerts/incidents
// status column — Active/Unsupervised/Missed/Closed) and the general-purpose
// `.pill.<color>` (camera/site/user status). Several words (Active, Closed)
// legitimately appear in BOTH families with OPPOSITE color meanings — an
// "Active" alert is bad (red), an "Active" site is good (green) — so which
// family applies can't be inferred from the string alone. Callers say which
// one they mean via `variant`.
const PILL_COLOR = {
  // Figma mock strings (Title Case)
  Online: 'green', Active: 'green', Enrolled: 'green',
  Partial: 'amber', Pending: 'amber',
  Offline: 'gray', Inactive: 'gray', Closed: 'gray',

  // Real backend enum values — uppercase
  ONLINE: 'green', ENABLED: 'green', SUPERVISED: 'green',
  ACKNOWLEDGED: 'amber', WAITING_FOR_ADULT: 'amber',
  OFFLINE: 'gray', DISABLED: 'gray', EMPTY: 'gray', UNKNOWN: 'gray', RESOLVED: 'gray',
  UNSUPERVISED: 'red', ACTIVE: 'red',
};

function humanize(status) {
  if (!/^[A-Z_]+$/.test(status)) return status;
  return status.toLowerCase().split('_').map((w) => w[0].toUpperCase() + w.slice(1)).join(' ');
}

export default function StatusPill({ status, variant }) {
  if (variant === 'alert') {
    const key = String(status ?? '').toLowerCase();
    return <span className={`status-pill ${key}`}>{humanize(status)}</span>;
  }
  const color = PILL_COLOR[status] || 'gray';
  return <span className={`pill ${color}`}>{humanize(status)}</span>;
}
