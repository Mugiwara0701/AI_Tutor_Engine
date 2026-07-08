// src/components/ui/ProgressBar.jsx
// Placeholder for ProgressBar — implement component/logic here.

// src/components/ui/ProgressBar.jsx

import { cn } from "../../utils/classNames.js";

const COLOR_STYLES = {
  primary: "bg-primary",
  green: "bg-green-500",
  orange: "bg-orange-500",
  red: "bg-red-500",
  purple: "bg-purple-500",
  slate: "bg-slate-400",
};

export default function ProgressBar({
  value = 0,
  label,
  showPercentage = true,
  color = "primary",
  size = "md",
  className,
}) {
  const clamped = Math.min(100, Math.max(0, value));
  const barColor = COLOR_STYLES[color] ?? COLOR_STYLES.primary;
  const height = size === "sm" ? "h-1.5" : size === "lg" ? "h-3" : "h-2";

  return (
    <div className={cn("w-full", className)}>
      {(label || showPercentage) && (
        <div className="flex items-center justify-between mb-1.5 text-xs">
          {label && <span className="text-slate-500">{label}</span>}
          {showPercentage && (
            <span className="font-medium text-slate-700">
              {Math.round(clamped)}%
            </span>
          )}
        </div>
      )}
      <div
        className={cn(
          "w-full rounded-full bg-slate-100 overflow-hidden",
          height,
        )}
      >
        <div
          className={cn(
            "h-full rounded-full transition-all duration-300",
            barColor,
          )}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}
