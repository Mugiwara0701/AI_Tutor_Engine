// src/utils/formatDuration.js
// Placeholder for formatDuration — implement component/logic here.

// src/utils/formatDuration.js

/**
 * Formats a duration in minutes into a short readable string,
 * e.g. 45 -> "45 min", 90 -> "1 hr 30 min", 120 -> "2 hr".
 */
export function formatDuration(minutes) {
  if (minutes == null || Number.isNaN(minutes)) return "—";
  if (minutes < 60) return `${minutes} min`;

  const hrs = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return mins === 0 ? `${hrs} hr` : `${hrs} hr ${mins} min`;
}
