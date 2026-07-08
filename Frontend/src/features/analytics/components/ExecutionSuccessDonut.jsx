// src/features/analytics/components/ExecutionSuccessDonut.jsx
// Placeholder for ExecutionSuccessDonut — implement component/logic here.

// src/features/analytics/components/ExecutionSuccessDonut.jsx

import { PieChart, Pie, Cell, ResponsiveContainer } from "recharts";

export default function ExecutionSuccessDonut({ data }) {
  const chartData = [
    { name: "Success", value: data.successPercent },
    { name: "Failed", value: data.failedPercent },
  ];
  const COLORS = ["#2563EB", "#ef4444"];

  return (
    <div className="bg-white border border-slate-100 rounded-card p-5 flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-slate-800">
        Execution Success
      </h3>

      <div className="relative h-48">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              dataKey="value"
              innerRadius={55}
              outerRadius={75}
              paddingAngle={2}
              stroke="none"
            >
              {chartData.map((entry, i) => (
                <Cell key={entry.name} fill={COLORS[i]} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span className="text-2xl font-bold text-slate-900">
            {data.successPercent}%
          </span>
          <span className="text-xs text-slate-400">Success</span>
        </div>
      </div>

      <div className="flex items-center justify-between text-sm border-t border-slate-50 pt-3">
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-primary" />
          <span className="text-slate-500">Success {data.successPercent}%</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-red-500" />
          <span className="text-slate-500">Failed {data.failedPercent}%</span>
        </div>
      </div>

      <p className="text-xs text-slate-400">
        {data.totalExecutions.toLocaleString()} total executions
      </p>
    </div>
  );
}
