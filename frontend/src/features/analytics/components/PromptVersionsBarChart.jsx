// src/features/analytics/components/PromptVersionsBarChart.jsx
// Placeholder for PromptVersionsBarChart — implement component/logic here.

// src/features/analytics/components/PromptVersionsBarChart.jsx

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

export default function PromptVersionsBarChart({ promptVersions }) {
  return (
    <div className="bg-white border border-slate-100 rounded-card p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-800">
          Prompt Versions
        </h3>
        <span className="text-xs text-slate-400">
          {promptVersions.totalVersions} total
        </span>
      </div>

      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={promptVersions.weeks}
            margin={{ top: 8, right: 8, bottom: 0, left: -20 }}
          >
            <CartesianGrid stroke="#f1f5f9" vertical={false} />
            <XAxis
              dataKey="week"
              tick={{ fontSize: 11, fill: "#94a3b8" }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#94a3b8" }}
              tickLine={false}
              axisLine={false}
            />
            <Bar
              dataKey="versions"
              fill="#2563EB"
              radius={[6, 6, 0, 0]}
              barSize={28}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
