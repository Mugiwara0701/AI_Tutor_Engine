// src/utils/formatBytes.js

/**
 * Formats a byte count into a human-readable string, e.g. 1536 -> "1.5 KB".
 */
export function formatBytes(bytes, decimals = 1) {
  if (bytes === 0 || bytes == null || Number.isNaN(bytes)) return "0 B";

  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const value = bytes / Math.pow(k, i);

  return `${value.toFixed(decimals)} ${sizes[i]}`;
}

/**
 * Formats a GB value (already in gigabytes) into a display string, e.g. 42.8 -> "42.8 GB".
 */
export function formatGB(gb, decimals = 1) {
  if (gb == null || Number.isNaN(gb)) return "0 GB";
  return `${gb.toFixed(decimals)} GB`;
}
