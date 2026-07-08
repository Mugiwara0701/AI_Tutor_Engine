// src/features/analytics/components/MetricsRow.jsx
// Placeholder for MetricsRow — implement component/logic here.

// src/features/analytics/components/MetricsRow.jsx

import { Clock, FileText, Presentation, CheckCircle2 } from "lucide-react";
import MetricCard from "../../../components/ui/MetricCard.jsx";

const ICONS = {
  avgGenTime: Clock,
  avgPromptLength: FileText,
  avgSlides: Presentation,
  extractionSuccess: CheckCircle2,
};

export default function MetricsRow({ metrics = [] }) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {metrics.map((metric) => (
        <MetricCard
          key={metric.key}
          icon={ICONS[metric.key]}
          label={metric.label}
          value={metric.value}
          trend={metric.changePercent}
        />
      ))}
    </div>
  );
}
