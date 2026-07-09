// src/features/pipeline-monitor/components/PipelineStagesList.jsx
// Placeholder for PipelineStagesList — implement component/logic here.

// src/features/pipeline-monitor/components/PipelineStagesList.jsx

import { cn } from "../../../utils/classNames.js";
import { formatTimeAgo } from "../../../utils/formatDate.js";

const DOT_STYLES = {
  Completed: "bg-green-500",
  "In Progress": "bg-primary",
  Pending: "bg-slate-300",
};

export default function PipelineStagesList({ stages = [] }) {
  return (
    <div className="bg-white border border-slate-100 rounded-card p-5">
      <h3 className="text-sm font-semibold text-slate-800 mb-4">
        Pipeline Stages
      </h3>

      <div className="flex flex-col gap-4">
        {stages.map((stage) => (
          <div key={stage.id} className="flex items-start gap-3">
            <span
              className={cn(
                "w-2.5 h-2.5 rounded-full mt-1.5 shrink-0",
                DOT_STYLES[stage.status] ?? "bg-slate-300",
              )}
            />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-slate-700 truncate">
                {stage.name}
              </p>
              <p className="text-xs text-slate-400">
                {stage.lastUpdate
                  ? formatTimeAgo(stage.lastUpdate)
                  : "Not started"}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
