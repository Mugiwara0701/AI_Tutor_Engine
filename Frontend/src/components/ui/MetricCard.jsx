// src/components/ui/MetricCard.jsx
// Placeholder for MetricCard — implement component/logic here.

// src/components/ui/MetricCard.jsx

import { TrendingUp, TrendingDown } from "lucide-react";
import { cn } from "../../utils/classNames.js";

export default function MetricCard({
  icon: Icon,
  label,
  value,
  trend,
  className,
}) {
  const isPositive = typeof trend === "number" ? trend >= 0 : null;

  return (
    <div
      className={cn(
        "bg-white border border-slate-100 rounded-card p-4 flex flex-col gap-2",
        className,
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-slate-500">{label}</span>
        {Icon && (
          <div className="w-7 h-7 rounded-btn bg-blue-50 flex items-center justify-center">
            <Icon className="w-4 h-4 text-primary" />
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
