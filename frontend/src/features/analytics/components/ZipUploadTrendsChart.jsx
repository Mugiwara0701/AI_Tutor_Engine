// src/features/analytics/components/ZipUploadTrendsChart.jsx
// Placeholder for ZipUploadTrendsChart — implement component/logic here.

// src/features/analytics/components/ZipUploadTrendsChart.jsx

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

export default function ZipUploadTrendsChart({ data = [] }) {
  return (
    <div className="bg-white border border-slate-100 rounded-card p-5 flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-slate-800">
        ZIP Upload Trends
      </h3>

      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={data}
            margin={{ top: 8, right: 8, bottom: 0, left: -20 }}
          >
            <CartesianGrid stroke="#f1f5f9" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: "#94a3b8" }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#94a3b8" }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              contentStyle={{
                borderRadius: 8,
                borderColor: "#e2e8f0",
                fontSize: 12,
              }}
            />
            <Line
              type="monotone"
              dataKey="uploads"
              stroke="#2563EB"
              strokeWidth={2}
              dot={{ r: 3, fill: "#2563EB" }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
