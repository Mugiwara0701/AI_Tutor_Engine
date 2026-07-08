// src/features/pipeline-monitor/components/SystemResourcesPanel.jsx
// Placeholder for SystemResourcesPanel — implement component/logic here.

// src/features/pipeline-monitor/components/SystemResourcesPanel.jsx

import ProgressBar from "../../../components/ui/ProgressBar.jsx";

export default function SystemResourcesPanel({ resources }) {
  if (!resources) return null;

  const resourceColor = (value) =>
    value > 85 ? "red" : value > 65 ? "orange" : "primary";

  return (
    <div className="bg-white border border-slate-100 rounded-card p-5 flex flex-col gap-4">
      <h3 className="text-sm font-semibold text-slate-800">System Resources</h3>

      <ProgressBar
        label="CPU Usage"
        value={resources.cpu}
        color={resourceColor(resources.cpu)}
        size="sm"
      />
      <ProgressBar
        label="RAM Usage"
        value={resources.ram}
        color={resourceColor(resources.ram)}
        size="sm"
      />
      <ProgressBar
        label="GPU Usage"
        value={resources.gpu}
        color={resourceColor(resources.gpu)}
        size="sm"
      />

      <div className="flex items-center justify-between pt-2 border-t border-slate-50">
        <span className="text-xs text-slate-500">Processing Speed</span>
        <span className="text-sm font-medium text-slate-800">
          {resources.processingSpeed.value} {resources.processingSpeed.unit}
        </span>
      </div>
    </div>
  );
}
