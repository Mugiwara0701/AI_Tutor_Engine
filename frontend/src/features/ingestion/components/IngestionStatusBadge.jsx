// src/features/ingestion/components/IngestionStatusBadge.jsx
//
// The Ingestion page uses its own status color mapping (blue = In
// Progress, green = Completed, red = Failed, grey = Queued/Pending) per
// the reference design. The shared StatusBadge component maps
// "in progress" to orange for other pages (e.g. ZIP Manager), so a small
// local badge is used here instead of changing that shared convention.

import { cn } from "../../../utils/classNames.js";

const STATUS_STYLES = {
  "in progress": "bg-blue-50 text-primary",
  completed: "bg-green-50 text-green-600",
  failed: "bg-red-50 text-red-600",
  queued: "bg-slate-100 text-slate-500",
  pending: "bg-slate-100 text-slate-500",
};

export default function IngestionStatusBadge({ status, className }) {
  const key = String(status ?? "").toLowerCase().trim();
  const style = STATUS_STYLES[key] ?? "bg-slate-100 text-slate-500";

  return (
    <span
      className={cn(
        "inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap",
        style,
        className,
      )}
    >
      {status}
    </span>
  );
}
