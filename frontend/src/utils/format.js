/** Formats a duration given in seconds as a short human string (e.g. "3h 12m", "45s"). Pure —
 * no Date.now() — so it's safe to call directly during render (e.g. from useMemo). */
export function formatSecondsDuration(totalSecondsInput) {
  const totalSeconds = Math.round(Math.max(0, totalSecondsInput));
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const totalMinutes = Math.round(totalSeconds / 60);
  if (totalMinutes < 60) return `${totalMinutes}m`;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`;
}
