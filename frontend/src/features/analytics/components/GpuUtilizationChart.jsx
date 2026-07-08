// src/features/analytics/components/GpuUtilizationChart.jsx
// Placeholder for GpuUtilizationChart — implement component/logic here.

// src/features/analytics/components/GpuUtilizationChart.jsx

import { TrendingUp, TrendingDown } from "lucide-react";
import { LineChart, Line, XAxis, ResponsiveContainer } from "recharts";
import { cn } from "../../../utils/classNames.js";

export default function GpuUtilizationChart({ gpuUtilization }) {
  const isPositive = gpuUtilization.changePercent >= 0;

  return (
    <div className="bg-white border border-slate-100 rounded-card p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-800">
          GPU Utilization
        </h3>
        <div className="flex items-center gap-1.5">
          <span className="text-lg font-bold text-slate-900">
            {gpuUtilization.currentPercent}%
          </span>
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
            {Math.abs(gpuUtilization.changePercent)}%
          </span>
        </div>
      </div>

      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={gpuUtilization.series}
            margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
          >
            <XAxis
              dataKey="time"
              tick={{ fontSize: 11, fill: "#94a3b8" }}
              tickLine={false}
              axisLine={false}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke="#a855f7"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
