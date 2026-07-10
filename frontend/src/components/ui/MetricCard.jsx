// src/components/ui/MetricCard.jsx

import { TrendingUp, TrendingDown } from "lucide-react";
import { cn } from "../../utils/classNames.js";

// Optional accent theme for the icon chip + top border. Defaults to the
// original blue treatment, so existing callers are unaffected.
const ACCENT_STYLES = {
  primary: { icon: "bg-blue-50 text-primary", bar: "bg-primary" },
  green: { icon: "bg-green-50 text-green-600", bar: "bg-green-500" },
  purple: { icon: "bg-purple-50 text-purple-600", bar: "bg-purple-500" },
  orange: { icon: "bg-orange-50 text-orange-600", bar: "bg-orange-500" },
  red: { icon: "bg-red-50 text-red-600", bar: "bg-red-500" },
  slate: { icon: "bg-slate-100 text-slate-500", bar: "bg-slate-400" },
};

export default function MetricCard({
  icon: Icon,
  label,
  value,
  trend,
  accent = "primary",
  className,
}) {
  const isPositive = typeof trend === "number" ? trend >= 0 : null;
  const theme = ACCENT_STYLES[accent] ?? ACCENT_STYLES.primary;

  return (
    <div
      className={cn(
        "relative overflow-hidden bg-white border border-slate-100 rounded-card p-4 flex flex-col gap-2 transition-shadow hover:shadow-sm",
        className,
      )}
    >
      <span className={cn("absolute top-0 left-0 h-1 w-full", theme.bar)} />

      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-slate-500">{label}</span>
        {Icon && (
          <div
            className={cn(
              "w-7 h-7 rounded-btn flex items-center justify-center",
              theme.icon,
            )}
          >
            <Icon className="w-4 h-4" />
          </div>
        )}
      </div>

      <div className="flex items-end justify-between">
        <span className="text-2xl font-semibold text-slate-900">{value}</span>
        {trend != null && (
          <span
            className={cn(
              "flex items-center gap-0.5 text-xs font-medium",
              isPositive ? "text-green-600" : "text-red-600",
            )}
          >
            {isPositive ? (
              <TrendingUp className="w-3.5 h-3.5" />
            ) : (
              <TrendingDown className="w-3.5 h-3.5" />
            )}
            {Math.abs(trend)}%
          </span>
        )}
      </div>
    </div>
  );
}
