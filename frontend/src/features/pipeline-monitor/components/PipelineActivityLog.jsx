// src/features/pipeline-monitor/components/PipelineActivityLog.jsx
// Placeholder for PipelineActivityLog — implement component/logic here.

// src/features/pipeline-monitor/components/PipelineActivityLog.jsx

import ActivityLogItem from "../../../components/shared/ActivityLogItem.jsx";

export default function PipelineActivityLog({ activityLog = [] }) {
  return (
    <div className="bg-white border border-slate-100 rounded-card p-5">
      <h3 className="text-sm font-semibold text-slate-800 mb-4">
        Activity Log
      </h3>

      <div className="flex flex-col gap-3">
        {activityLog.map((entry) => (
          <ActivityLogItem
            key={entry.id}
            action={entry.message}
            timestamp={entry.timestamp}
            color={entry.color}
          />
        ))}
      </div>
    </div>
  );
}
