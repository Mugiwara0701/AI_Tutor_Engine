// src/components/ui/StatusBadge.jsx
// Placeholder for StatusBadge — implement component/logic here.

// src/components/ui/StatusBadge.jsx

import { cn } from "../../utils/classNames.js";

// Central status -> style map used across every phase.
// Keys are matched case-insensitively so mock data can use natural labels.
const STATUS_STYLES = {
  complete: "bg-green-50 text-green-600",
  completed: "bg-green-50 text-green-600",
  active: "bg-green-50 text-green-600",
  success: "bg-green-50 text-green-600",

  "in progress": "bg-orange-50 text-orange-600",
  processing: "bg-orange-50 text-orange-600",

  "not started": "bg-slate-100 text-slate-500",
  pending: "bg-slate-100 text-slate-500",
  inactive: "bg-slate-100 text-slate-500",
  draft: "bg-slate-100 text-slate-500",

  failed: "bg-red-50 text-red-600",
  error: "bg-red-50 text-red-600",
};

const DOT_STYLES = {
  complete: "bg-green-500",
  completed: "bg-green-500",
  active: "bg-green-500",
  success: "bg-green-500",
  "in progress": "bg-orange-500",
  processing: "bg-orange-500",
  "not started": "bg-slate-400",
  pending: "bg-slate-400",
  inactive: "bg-slate-400",
  draft: "bg-slate-400",
  failed: "bg-red-500",
  error: "bg-red-500",
};

export default function StatusBadge({ status, className, showDot = true }) {
  const key = String(status ?? "")
    .toLowerCase()
    .trim();
  const style = STATUS_STYLES[key] ?? "bg-slate-100 text-slate-500";
  const dot = DOT_STYLES[key] ?? "bg-slate-400";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap",
        style,
        className,
      )}
    >
      {showDot && <span className={cn("w-1.5 h-1.5 rounded-full", dot)} />}
      {status}
    </span>
  );
}
