// src/utils/formatDate.js

/**
 * Formats an ISO date string or Date into a short readable form, e.g. "Jul 5, 2026".
 */
export function formatDate(input) {
  if (!input) return "—";
  const date = input instanceof Date ? input : new Date(input);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/**
 * Formats a date as a relative "time ago" string, e.g. "2 days ago", "5 hours ago".
 * Falls back to formatDate for anything older than ~30 days.
 */
export function formatTimeAgo(input) {
  if (!input) return "—";
  const date = input instanceof Date ? input : new Date(input);
  if (Number.isNaN(date.getTime())) return "—";

  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return "Just now";

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min${minutes === 1 ? "" : "s"} ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;

  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} day${days === 1 ? "" : "s"} ago`;

  const weeks = Math.floor(days / 7);
  if (weeks < 5) return `${weeks} week${weeks === 1 ? "" : "s"} ago`;

  return formatDate(date);
}
