// src/features/pipeline-monitor/components/PipelineStatsRow.jsx

import { cn } from "../../../utils/classNames.js";
import SparklineChart from "../../../components/ui/SparklineChart.jsx";

const TEXT_COLORS = {
  primary: "text-primary",
  green: "text-green-600",
  purple: "text-purple-600",
  orange: "text-orange-600",
  red: "text-red-600",
};

export default function PipelineStatsRow({ stats = [] }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
      {stats.map((stat) => (
        <div
          key={stat.key}
          className="bg-white border border-slate-100 rounded-card p-4 flex flex-col gap-2"
        >
          <span className="text-xs font-medium text-slate-500">
            {stat.label}
          </span>

          <div className="flex items-end justify-between">
            <div>
              <p className="text-2xl font-semibold text-slate-900">
                {stat.count}
              </p>
              <p
                className={cn(
                  "text-xs font-medium",
                  TEXT_COLORS[stat.color] ?? "text-slate-500",
                )}
              >
                {stat.percentage}%
              </p>
            </div>
            <SparklineChart data={stat.trend} color={stat.color} />
          </div>
        </div>
      ))}
    </div>
  );
}
