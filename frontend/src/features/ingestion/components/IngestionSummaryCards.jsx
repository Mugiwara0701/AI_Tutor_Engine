// src/features/ingestion/components/IngestionSummaryCards.jsx

import { UploadCloud, Clock, CheckCircle2, XCircle } from "lucide-react";
import MetricCard from "../../../components/ui/MetricCard.jsx";

export default function IngestionSummaryCards({ summary }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <MetricCard
        icon={UploadCloud}
        label="Books Uploaded"
        value={summary.uploaded.count}
        trend={summary.uploaded.trend}
        trendLabel="vs last month"
        accent="primary"
      />
      <MetricCard
        icon={Clock}
        label="Processing"
        value={summary.processing.count}
        trend={summary.processing.trend}
        trendLabel="vs last month"
        accent="orange"
      />
      <MetricCard
        icon={CheckCircle2}
        label="Completed"
        value={summary.completed.count}
        trend={summary.completed.trend}
        trendLabel="vs last month"
        accent="green"
      />
      <MetricCard
        icon={XCircle}
        label="Failed"
        value={summary.failed.count}
        trend={summary.failed.trend}
        trendLabel="vs last month"
        accent="red"
      />
    </div>
  );
}
