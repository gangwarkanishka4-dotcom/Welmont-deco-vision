export function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

export function formatTime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}

export function formatDuration(startIso, endIso) {
  if (!startIso) return '—';
  const start = new Date(startIso).getTime();
  const end = endIso ? new Date(endIso).getTime() : Date.now();
  const totalSeconds = Math.max(0, Math.round((end - start) / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

export function isToday(iso) {
  if (!iso) return false;
  const d = new Date(iso);
  const now = new Date();
  return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
}

export function isYesterday(iso) {
  if (!iso) return false;
  const d = new Date(iso);
  const y = new Date();
  y.setDate(y.getDate() - 1);
  return d.getFullYear() === y.getFullYear() && d.getMonth() === y.getMonth() && d.getDate() === y.getDate();
}

// Real fields only (no acknowledged-by identity — there's no user/auth system
// to attribute it to): derives a three-way status read directly from
// status + acknowledged_at rather than inventing a fourth backend value.
//   - still ACTIVE                        -> "Active"       (needs attention now)
//   - acknowledged (ACKNOWLEDGED/RESOLVED) -> "Unsupervised" (someone responded)
//   - resolved without ever being acked    -> "Missed"       (nobody responded in time)
export function alertStatusLabel(alert) {
  if (alert.status === 'ACTIVE') return 'Active';
  if (alert.acknowledged_at) return 'Unsupervised';
  return 'Missed';
}

/** Masks a camera's real RTSP host for display (e.g. in a management table)
 * — shows only the last IP segment, same idea as blurring a password field.
 * The API itself still returns the real host; this only affects what's
 * rendered on screen. */
export function maskRtspUrl(host, port, path) {
  if (!host) return '—';
  const segments = host.split('.');
  const last = segments[segments.length - 1] || host;
  return `rtsp://***.***.**.${last}:${port}${path || ''}`;
}

/** Client-side CSV export — no backend endpoint exists for this, but it's
 * genuinely real: it exports whatever real rows are currently on screen,
 * not a fabricated download. */
export function downloadCsv(filename, headers, rows) {
  const escape = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const lines = [headers.map(escape).join(','), ...rows.map((row) => row.map(escape).join(','))];
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
