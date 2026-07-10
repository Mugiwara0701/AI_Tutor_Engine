// src/features/dashboard/components/QuickStatsRow.jsx

import { Layers, Activity, HardDrive, CheckCircle2 } from "lucide-react";
import MetricCard from "../../../components/ui/MetricCard.jsx";
import { formatGB } from "../../../utils/formatBytes.js";

export default function QuickStatsRow({ stats }) {
  const items = [
    {
      key: "totalTopics",
      label: "Total Topics",
      value: stats.totalTopics.toLocaleString(),
      icon: Layers,
      trend: stats.topicsTrend,
      accent: "primary",
    },
    {
      key: "activePipelines",
      label: "Active Pipelines",
      value: stats.activePipelines,
      icon: Activity,
      trend: stats.activePipelinesTrend,
      accent: "purple",
    },
    {
      key: "storageUsed",
      label: "Storage Used",
      value: `${formatGB(stats.storageUsedGB)} / ${formatGB(stats.storageTotalGB)}`,
      icon: HardDrive,
      trend: null,
      accent: "orange",
    },
    {
      key: "successRate",
      label: "Success Rate",
      value: `${stats.successRate}%`,
      icon: CheckCircle2,
      trend: stats.successRateTrend,
      accent: "green",
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {items.map((item) => (
        <MetricCard
          key={item.key}
          icon={item.icon}
          label={item.label}
          value={item.value}
          trend={item.trend}
          accent={item.accent}
        />
      ))}
    </div>
  );
}
