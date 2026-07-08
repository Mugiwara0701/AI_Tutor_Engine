// src/features/pipeline-monitor/pages/PipelineMonitorPage.jsx
// Placeholder for PipelineMonitorPage — implement component/logic here.

// src/features/pipeline-monitor/pages/PipelineMonitorPage.jsx

import { Eye, Plus } from "lucide-react";
import { usePipelineData } from "../hooks/usePipelineData.js";
import PipelineSummaryCard from "../components/PipelineSummaryCard.jsx";
import PipelineStatsRow from "../components/PipelineStatsRow.jsx";
import PipelineExecutionTable from "../components/PipelineExecutionTable.jsx";
import PipelineStagesList from "../components/PipelineStagesList.jsx";
import SystemResourcesPanel from "../components/SystemResourcesPanel.jsx";
import PipelineActivityLog from "../components/PipelineActivityLog.jsx";

export default function PipelineMonitorPage() {
  const { pipeline, stages, stats, resources, activityLog, elapsedMinutes } =
    usePipelineData();

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Pipeline Monitor
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Track content generation pipelines in real time.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-btn border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
          >
            <Eye className="w-4 h-4" />
            View All Pipelines
          </button>
          <button
            type="button"
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-btn bg-primary text-white text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            <Plus className="w-4 h-4" />
            New Pipeline
          </button>
        </div>
      </div>

      <PipelineSummaryCard
        pipeline={pipeline}
        elapsedMinutes={elapsedMinutes}
      />

      <PipelineStatsRow stats={stats} />

      <div className="flex flex-col lg:flex-row gap-5 items-start">
        <div className="flex-1 min-w-0">
          <PipelineExecutionTable stages={stages} />
        </div>

        <div className="w-full lg:w-80 shrink-0 flex flex-col gap-5">
          <PipelineStagesList stages={stages} />
          <SystemResourcesPanel resources={resources} />
          <PipelineActivityLog activityLog={activityLog} />
        </div>
      </div>
    </div>
  );
}
