/** Formats the elapsed time between an ISO timestamp and now as a short human duration (e.g. "3h 12m", "45s"). */
export function formatDuration(iso: string): string {
  const ms = Math.max(0, Date.now() - new Date(iso).getTime());
  const totalSeconds = Math.round(ms / 1000);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const totalMinutes = Math.round(totalSeconds / 60);
  if (totalMinutes < 60) return `${totalMinutes}m`;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`;
}
