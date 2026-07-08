// src/components/ui/VersionBadge.jsx
// Placeholder for VersionBadge — implement component/logic here.

// src/components/ui/VersionBadge.jsx

import { cn } from "../../utils/classNames.js";

export default function VersionBadge({ version, isLatest = false, className }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium",
        isLatest ? "bg-blue-50 text-primary" : "bg-slate-100 text-slate-500",
        className,
      )}
    >
      {version}
      {isLatest && (
        <span className="text-[10px] uppercase tracking-wide">Latest</span>
      )}
    </span>
  );
}
