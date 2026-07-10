// src/features/dashboard/components/WeeklySummaryCard.jsx

import { Layers, Activity, CheckCircle2 } from "lucide-react";

export default function WeeklySummaryCard({ summary }) {
  const rows = [
    {
      key: "topicsAdded",
      label: "Topics added",
      value: summary.topicsAdded,
      icon: Layers,
      accent: "text-primary bg-blue-50",
    },
    {
      key: "pipelinesRun",
      label: "Pipelines run",
      value: summary.pipelinesRun,
      icon: Activity,
      accent: "text-purple-600 bg-purple-50",
    },
    {
      key: "avgSuccessRate",
      label: "Avg. success rate",
      value: `${summary.avgSuccessRate}%`,
      icon: CheckCircle2,
      accent: "text-green-600 bg-green-50",
    },
  ];

  return (
    <div className="bg-white border border-slate-100 rounded-card p-4">
      <h3 className="text-sm font-semibold text-slate-900 mb-3">This Week</h3>
      <div className="flex flex-col gap-3">
        {rows.map(({ key, label, value, icon: Icon, accent }) => (
          <div key={key} className="flex items-center gap-3">
            <div
              className={`w-8 h-8 rounded-btn flex items-center justify-center shrink-0 ${accent}`}
            >
              <Icon className="w-4 h-4" />
            </div>
            <span className="text-sm text-slate-600 flex-1">{label}</span>
            <span className="text-sm font-semibold text-slate-900">
              {value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
