// src/features/analytics/components/ComplexChaptersBarChart.jsx
// Placeholder for ComplexChaptersBarChart — implement component/logic here.

// src/features/analytics/components/ComplexChaptersBarChart.jsx

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Cell,
} from "recharts";

export default function ComplexChaptersBarChart({ data = [] }) {
  return (
    <div className="bg-white border border-slate-100 rounded-card p-5 flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-slate-800">
        Most Complex Chapters
      </h3>

      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 0, right: 16, bottom: 0, left: 0 }}
          >
            <XAxis type="number" domain={[0, 100]} hide />
            <YAxis
              type="category"
              dataKey="name"
              width={160}
              tick={{ fontSize: 11, fill: "#64748b" }}
              tickLine={false}
              axisLine={false}
            />
            <Bar dataKey="complexity" radius={[0, 6, 6, 0]} barSize={14}>
              {data.map((entry, i) => (
                <Cell key={entry.name} fill={i === 0 ? "#2563EB" : "#93c5fd"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
